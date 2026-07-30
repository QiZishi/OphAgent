import {
  AudioLines,
  AtSign,
  FileAudio,
  FileText,
  Image,
  Library,
  Mic,
  Paperclip,
  Plus,
  Send,
  Sparkles,
  Square,
  StopCircle,
  X
} from "lucide-react";
import { ClipboardEvent, DragEvent, FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { PLUGINS } from "../features/plugins";
import type { AttachmentRecord, LocalAttachment, PluginId, RunIntervention, SkillRecord } from "../types";
import { LoadingDots } from "./LoadingDots";

interface ComposerProps {
  value: string;
  attachments: LocalAttachment[];
  plugins: PluginId[];
  skills: SkillRecord[];
  selectedSkills: string[];
  submitting: boolean;
  running: boolean;
  interventionMode: "interrupt" | "queue";
  queuedInterventions: RunIntervention[];
  onValue: (value: string) => void;
  onFiles: (files: File[]) => void;
  onRemoveFile: (key: string) => void;
  onTogglePlugin: (id: PluginId) => void;
  onToggleSkill: (id: string) => void;
  onSubmit: (textOverride?: string) => Promise<void> | void;
  onStop: () => void;
  onInterventionMode: (mode: "interrupt" | "queue") => void;
  onCancelIntervention: (id: string) => void;
  onTranscribe: (file: File) => Promise<string>;
  onSpeak: (text: string, signal?: AbortSignal) => Promise<Blob>;
  onListFiles: () => Promise<AttachmentRecord[]>;
  onChooseExisting: (attachment: AttachmentRecord) => void;
  asrAvailable: boolean;
  ttsAvailable: boolean;
  latestAnswer?: string;
}

export function Composer(props: ComposerProps) {
  const { latestAnswer, onSpeak, ttsAvailable } = props;
  const queuedInterventions = props.queuedInterventions || [];
  const [addOpen, setAddOpen] = useState(false);
  const [pluginOpen, setPluginOpen] = useState(false);
  const [skillOpen, setSkillOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [voiceState, setVoiceState] = useState<"idle" | "requesting" | "recording" | "transcribing" | "error">("idle");
  const [voiceError, setVoiceError] = useState("");
  const [realtimeOpen, setRealtimeOpen] = useState(false);
  const [realtimeListening, setRealtimeListening] = useState(false);
  const [realtimePhase, setRealtimePhase] = useState<"idle" | "listening" | "transcribing" | "waiting" | "speaking" | "ready" | "error">("idle");
  const [spokenAudioUrl, setSpokenAudioUrl] = useState("");
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryItems, setLibraryItems] = useState<AttachmentRecord[]>([]);
  const [toolNotice, setToolNotice] = useState("");
  const composing = useRef(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const popoverArea = useRef<HTMLDivElement>(null);
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const mediaStream = useRef<MediaStream | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const recordingPurpose = useRef<"dictation" | "conversation">("dictation");
  const discardRecording = useRef(false);
  const spokenAudio = useRef<HTMLAudioElement | null>(null);
  const spokenAudioUrlRef = useRef("");
  const lastSpokenAnswer = useRef("");
  const speechAbort = useRef<AbortController | null>(null);
  const realtimeDialog = useRef<HTMLElement | null>(null);
  const realtimePreviousFocus = useRef<HTMLElement | null>(null);
  const selectedPluginNames = PLUGINS
    .filter((item) => props.plugins.includes(item.id))
    .map((item) => item.label);
  const selectedSkillNames = props.skills
    .filter((item) => props.selectedSkills.includes(item.id))
    .map((item) => item.id.replaceAll("_", " "));

  useEffect(() => {
    if (!textarea.current) return;
    textarea.current.style.height = "0px";
    textarea.current.style.height = `${Math.min(textarea.current.scrollHeight, 180)}px`;
  }, [props.value]);

  useEffect(() => {
    if (!addOpen && !pluginOpen && !skillOpen) return;
    const close = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        setAddOpen(false);
        setPluginOpen(false);
        setSkillOpen(false);
        setLibraryOpen(false);
      }
    };
    window.addEventListener("keydown", close);
    const closeOutside = (event: PointerEvent) => {
      if (!popoverArea.current?.contains(event.target as Node)) {
        setAddOpen(false);
        setPluginOpen(false);
        setSkillOpen(false);
      }
    };
    window.addEventListener("pointerdown", closeOutside);
    return () => {
      window.removeEventListener("keydown", close);
      window.removeEventListener("pointerdown", closeOutside);
    };
  }, [addOpen, pluginOpen, skillOpen]);

  async function openLibrary() {
    setLibraryOpen((value) => !value);
    if (libraryItems.length) return;
    setLibraryLoading(true);
    try {
      setLibraryItems(await props.onListFiles());
    } catch (reason) {
      setVoiceError(reason instanceof Error ? reason.message : "文件库加载失败");
    } finally {
      setLibraryLoading(false);
    }
  }

  useEffect(() => () => {
    discardRecording.current = true;
    if (mediaRecorder.current?.state === "recording") mediaRecorder.current.stop();
    mediaStream.current?.getTracks().forEach((track) => track.stop());
    spokenAudio.current?.pause();
    speechAbort.current?.abort();
    if (spokenAudioUrlRef.current) URL.revokeObjectURL(spokenAudioUrlRef.current);
  }, []);

  useEffect(() => {
    if (!realtimeOpen || !latestAnswer || latestAnswer === lastSpokenAnswer.current) return;
    lastSpokenAnswer.current = latestAnswer;
    const segments = splitRealtimeSpeech(latestAnswer.replace(/[#>*_`[\]]/g, ""));
    let cancelled = false;
    const controller = new AbortController();
    speechAbort.current?.abort();
    speechAbort.current = controller;
    const speak = async () => {
      setRealtimePhase("speaking");
      try {
        if (!ttsAvailable) throw new Error("服务端 TTS 未配置");
        for (const segment of segments) {
          const blob = await onSpeak(segment, controller.signal);
          if (cancelled || controller.signal.aborted) return;
          if (spokenAudioUrlRef.current) URL.revokeObjectURL(spokenAudioUrlRef.current);
          const url = URL.createObjectURL(blob);
          spokenAudioUrlRef.current = url;
          setSpokenAudioUrl(url);
          const audio = new Audio(url);
          spokenAudio.current = audio;
          await new Promise<void>((resolve, reject) => {
            audio.onended = () => resolve();
            audio.onerror = () => reject(new Error("语音播放失败"));
            audio.play().catch(reject);
          });
        }
        if (!cancelled) setRealtimePhase("idle");
      } catch (reason) {
        if (cancelled || controller.signal.aborted) return;
        setRealtimePhase("ready");
        setVoiceError(reason instanceof Error
          ? `${reason.message}；回答已保留为文字。`
          : "语音播放失败，回答已保留为文字。");
      }
    };
    void speak();
    return () => {
      cancelled = true;
      controller.abort();
      spokenAudio.current?.pause();
    };
  }, [latestAnswer, onSpeak, realtimeOpen, ttsAvailable]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if ((props.value.trim() || props.attachments.length) && !props.submitting) props.onSubmit();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !composing.current && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  function acceptFiles(files: File[]) {
    const supported = files.filter((file) =>
      file.type.startsWith("image/")
      || file.type.startsWith("audio/")
      || [".pdf", ".txt", ".md"].some((suffix) => file.name.toLowerCase().endsWith(suffix))
    );
    if (supported.length) {
      props.onFiles(supported);
      setAddOpen(false);
      setLibraryOpen(false);
    }
    if (supported.length !== files.length) {
      setToolNotice("部分文件类型不受支持；仅接受眼科影像、音频、PDF、TXT 和 Markdown。");
    }
  }

  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const images = Array.from(event.clipboardData.files).filter((file) => file.type.startsWith("image/"));
    if (images.length) acceptFiles(images);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    acceptFiles(Array.from(event.dataTransfer.files));
  }

  async function startDictation(autoSend = false) {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setVoiceState("error");
      setVoiceError("当前浏览器不支持录音，请改用音频文件上传。");
      return;
    }
    setVoiceState("requesting");
    setVoiceError("");
    discardRecording.current = false;
    recordingPurpose.current = autoSend ? "conversation" : "dictation";
    if (autoSend) {
      setRealtimePhase("listening");
      setRealtimeListening(true);
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaStream.current = stream;
      mediaRecorder.current = recorder;
      audioChunks.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) audioChunks.current.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        mediaStream.current = null;
        setRealtimeListening(false);
        if (discardRecording.current) {
          discardRecording.current = false;
          setVoiceState("idle");
          return;
        }
        const blob = new Blob(audioChunks.current, { type: recorder.mimeType || "audio/webm" });
        if (!blob.size) {
          setVoiceState("error");
          setVoiceError("没有录到声音，请检查麦克风后重试。");
          return;
        }
        setVoiceState("transcribing");
        if (recordingPurpose.current === "conversation") setRealtimePhase("transcribing");
        try {
          const extension = blob.type.includes("mp4") ? "m4a" : "webm";
          const text = await props.onTranscribe(new File([blob], `dictation-${Date.now()}.${extension}`, { type: blob.type }));
          const combined = [props.value.trim(), text.trim()].filter(Boolean).join(props.value.trim() ? "\n" : "");
          props.onValue(combined);
          setVoiceState("idle");
          if (recordingPurpose.current === "conversation") {
            setRealtimePhase("waiting");
            await props.onSubmit(combined);
          }
          requestAnimationFrame(() => textarea.current?.focus());
        } catch (reason) {
          setVoiceState("error");
          if (recordingPurpose.current === "conversation") setRealtimePhase("error");
          setVoiceError(reason instanceof Error ? reason.message : "语音转写失败");
        }
      };
      recorder.start();
      setVoiceState("recording");
    } catch (reason) {
      setVoiceState("error");
      setRealtimeListening(false);
      if (autoSend) setRealtimePhase("error");
      setVoiceError(reason instanceof Error && reason.name === "NotAllowedError"
        ? "麦克风权限被拒绝，请在浏览器设置中允许后重试。"
        : "无法启动麦克风，请检查输入设备。");
    }
  }

  function stopDictation() {
    if (mediaRecorder.current?.state === "recording") mediaRecorder.current.stop();
  }

  function startRealtime() {
    setVoiceError("");
    lastSpokenAnswer.current = props.latestAnswer || "";
    realtimePreviousFocus.current = document.activeElement as HTMLElement | null;
    setRealtimeOpen(true);
    if (!props.asrAvailable) {
      setRealtimePhase("error");
      setVoiceError("服务端 ASR 尚未配置，无法开始语音对话。");
      return;
    }
    void startDictation(true);
  }

  const closeRealtime = useCallback(() => {
    if (mediaRecorder.current?.state === "recording") {
      discardRecording.current = true;
      mediaRecorder.current.stop();
    }
    setRealtimeListening(false);
    setRealtimeOpen(false);
    setRealtimePhase("idle");
    spokenAudio.current?.pause();
    speechAbort.current?.abort();
    speechAbort.current = null;
    spokenAudio.current = null;
    if (spokenAudioUrlRef.current) URL.revokeObjectURL(spokenAudioUrlRef.current);
    spokenAudioUrlRef.current = "";
    setSpokenAudioUrl("");
    requestAnimationFrame(() => realtimePreviousFocus.current?.focus());
  }, []);

  useEffect(() => {
    if (!realtimeOpen) return;
    const dialog = realtimeDialog.current;
    const focusable = () => Array.from(
      dialog?.querySelectorAll<HTMLElement>(
        "button, audio[controls], [href], input, textarea, [tabindex]:not([tabindex='-1'])"
      ) || []
    );
    focusable()[0]?.focus();
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRealtime();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [closeRealtime, realtimeOpen]);

  return (
    <div
      ref={popoverArea}
      className={`composer-wrap ${dragging ? "dragging" : ""}`}
      onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setAddOpen(false);
          setPluginOpen(false);
          setSkillOpen(false);
        }
      }}
    >
      {queuedInterventions.length > 0 && (
        <div className="intervention-queue" aria-label="排队中的追加要求">
          {queuedInterventions.map((item) => (
            <div className="intervention-chip" key={item.id}>
              <span>
                <strong>等待下一执行节点</strong>
                <small>{item.content || `已附加 ${item.attachment_ids.length} 个文件`}</small>
              </span>
              <button
                type="button"
                onClick={() => props.onCancelIntervention(item.id)}
                aria-label={`取消排队要求：${item.content || "附件"}`}
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
      {props.attachments.length > 0 && (
        <div className="attachment-strip" aria-label="待发送附件">
          {props.attachments.map((attachment) => (
              <div className={`attachment-chip status-${attachment.status}`} key={attachment.key}>
              {attachment.preview ? <img src={attachment.preview} alt="" /> : attachment.file.type.startsWith("audio/") ? <FileAudio size={18} /> : <FileText size={18} />}
              <span><strong>{attachment.file.name}</strong><small>{formatBytes(attachment.uploaded?.size ?? attachment.file.size)} · {attachment.status === "uploading" ? "上传中" : attachment.status === "failed" ? "上传失败" : attachment.status === "uploaded" ? "来自文件库" : "待发送"}</small></span>
              {attachment.status === "uploading" ? <LoadingDots label="附件上传中" /> : <button onClick={() => props.onRemoveFile(attachment.key)} aria-label={`移除 ${attachment.file.name}`}><X size={14} /></button>}
            </div>
          ))}
        </div>
      )}
      <form className="composer" onSubmit={submit}>
        <label className="sr-only" htmlFor="ophagent-composer">向 OphAgent 提问</label>
        <textarea
          ref={textarea}
          id="ophagent-composer"
          value={props.value}
          onChange={(event) => props.onValue(event.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          onCompositionStart={() => { composing.current = true; }}
          onCompositionEnd={() => { composing.current = false; }}
          placeholder={props.running ? "补充信息或改变方向…" : "向 OphAgent 提问"}
          rows={1}
        />
        <div className="composer-toolbar">
          <div className="composer-popover-wrap">
            <button type="button" className="tool-button" onClick={() => { setAddOpen((value) => !value); setPluginOpen(false); setSkillOpen(false); }} aria-label="添加附件" aria-expanded={addOpen}><Plus size={19} /></button>
            {addOpen && (
              <div className="composer-popover add-menu">
                <label><Image size={17} />上传影像<input hidden multiple type="file" accept="image/*" onChange={(event) => acceptFiles(Array.from(event.target.files || []))} /></label>
                <label><FileText size={17} />上传文档<input hidden multiple type="file" accept=".pdf,.txt,.md" onChange={(event) => acceptFiles(Array.from(event.target.files || []))} /></label>
                <label><FileAudio size={17} />上传音频<input hidden multiple type="file" accept="audio/*" onChange={(event) => acceptFiles(Array.from(event.target.files || []))} /></label>
                <button type="button" onClick={openLibrary} aria-expanded={libraryOpen}><Library size={17} />从文件库选择</button>
                {libraryOpen && (
                  <div className="file-library-picker">
                    {libraryLoading && <span><LoadingDots label="读取文件库" />正在读取私人文件…</span>}
                    {!libraryLoading && libraryItems.map((item) => (
                      <button
                        type="button"
                        key={item.id}
                        onClick={() => {
                          props.onChooseExisting(item);
                          setAddOpen(false);
                          setLibraryOpen(false);
                        }}
                      >
                        {item.kind === "image" ? <Image size={16} /> : item.kind === "audio" ? <FileAudio size={16} /> : <FileText size={16} />}
                        <span><strong>{item.original_filename}</strong><small>{formatBytes(item.size)}</small></span>
                      </button>
                    ))}
                    {!libraryLoading && !libraryItems.length && <span>文件库为空，可先上传一个文件。</span>}
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="composer-popover-wrap">
            <button type="button" className={`plugin-trigger ${props.plugins.length ? "selected" : ""}`} onClick={() => { setPluginOpen((value) => !value); setAddOpen(false); setSkillOpen(false); }} aria-expanded={pluginOpen}>
              <AtSign size={17} />{selectedPluginNames.length ? selectedPluginNames.join("、") : "插件"}
            </button>
            {pluginOpen && (
              <div className="composer-popover plugin-menu">
                <header><strong>选择插件</strong><small>不选时由 OphAgent 自动判断</small></header>
                {PLUGINS.map(({ id, label, description, icon: Icon }) => (
                  <button type="button" className={props.plugins.includes(id) ? "selected" : ""} onClick={() => props.onTogglePlugin(id)} key={id}>
                    <Icon size={18} /><span><strong>{label}</strong><small>{description}</small></span>
                    <span className="plugin-check">{props.plugins.includes(id) ? "✓" : ""}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="composer-popover-wrap">
            <button
              type="button"
              className={`skill-trigger ${props.selectedSkills.length ? "selected" : ""}`}
              onClick={() => {
                setSkillOpen((value) => !value);
                setAddOpen(false);
                setPluginOpen(false);
              }}
              aria-label="技能"
              aria-expanded={skillOpen}
            >
              <Sparkles size={17} />
              {selectedSkillNames.length ? selectedSkillNames.join("、") : "技能"}
            </button>
            {skillOpen && (
              <div className="composer-popover skill-menu">
                <header>
                  <strong>本次使用的技能</strong>
                  <small>只列出已验证并启用的技能；不选择时由 OphAgent 自动匹配。</small>
                </header>
                {props.skills.map((skill) => (
                  <button
                    type="button"
                    key={skill.id}
                    className={props.selectedSkills.includes(skill.id) ? "selected" : ""}
                    onClick={() => props.onToggleSkill(skill.id)}
                  >
                    <Sparkles size={17} />
                    <span><strong>{skill.id.replaceAll("_", " ")}</strong><small>{skill.description}</small></span>
                    <span className="plugin-check">{props.selectedSkills.includes(skill.id) ? "✓" : ""}</span>
                  </button>
                ))}
                {!props.skills.length && (
                  <p>暂无已启用技能。请在左侧“技能”中导入、验证并启用后再选择。</p>
                )}
              </div>
            )}
          </div>
          <span className="composer-spacer" />
          {voiceState === "recording" ? (
            <button type="button" className="voice-button recording" onClick={stopDictation} aria-label="停止录音并转写"><StopCircle size={18} /></button>
          ) : (
            <button
              type="button"
              className={`voice-button ${voiceState}`}
              onClick={() => startDictation(false)}
              disabled={voiceState === "requesting" || voiceState === "transcribing"}
              aria-label={voiceState === "transcribing" ? "正在转写语音" : "语音输入"}
            >
              {voiceState === "requesting" || voiceState === "transcribing" ? <LoadingDots label="语音处理中" /> : <Mic size={18} />}
            </button>
          )}
          <button type="button" className={`voice-button ${realtimeOpen ? "active" : ""}`} onClick={realtimeOpen ? closeRealtime : startRealtime} aria-label="实时语音模式"><AudioLines size={18} /></button>
          {props.running && (
            <div className="intervention-mode" role="group" aria-label="运行中追加要求的处理方式">
              <button
                type="button"
                className={props.interventionMode === "queue" ? "selected" : ""}
                onClick={() => props.onInterventionMode("queue")}
                aria-label="排队追加：在智能体进入下一个执行节点前加入新要求"
              >
                排队
              </button>
              <button
                type="button"
                className={props.interventionMode === "interrupt" ? "selected interrupt" : "interrupt"}
                onClick={() => props.onInterventionMode("interrupt")}
                aria-label="立即打断：中断当前步骤并带着新要求从检查点继续"
              >
                打断
              </button>
            </div>
          )}
          {props.running && (
            <button type="button" className="stop-button" onClick={props.onStop} aria-label="停止当前任务"><Square size={14} />停止</button>
          )}
          <button
            className={`send-button ${props.running ? "intervention-send" : ""}`}
            disabled={props.submitting || (!props.value.trim() && !props.attachments.length)}
            aria-label={
              props.running
                ? props.interventionMode === "interrupt"
                  ? "立即打断并发送新要求"
                  : "将新要求排队发送"
                : "发送"
            }
          >
            {props.submitting ? <LoadingDots label="发送中" /> : <Send size={18} />}
          </button>
        </div>
      </form>
      {dragging && <div className="drop-hint"><Paperclip size={18} />松开即可添加文件</div>}
      {voiceError && <div className="voice-error" role="alert">{voiceError}<button onClick={() => { setVoiceError(""); if (voiceState === "error") setVoiceState("idle"); }}>关闭</button></div>}
      {toolNotice && <div className="composer-status" role="status">{toolNotice}<button onClick={() => setToolNotice("")}>关闭</button></div>}
      {realtimeOpen && (
        <>
        <button className="voice-dialog-scrim" aria-label="退出语音对话" onClick={closeRealtime} />
        <section ref={realtimeDialog} className="realtime-voice" role="dialog" aria-modal="true" aria-label="语音对话模式">
          <header><span className={`clinical-pulse ${realtimeListening ? "listening" : ""}`} /><div><strong>语音对话</strong><small>{voicePhaseLabel(realtimePhase, props.ttsAvailable)}</small></div><button className="icon-button" onClick={closeRealtime} aria-label="退出语音对话"><X size={18} /></button></header>
          <div className="realtime-transcript">{props.value || "点击开始说话；结束后将转写并直接提问。"}</div>
          {spokenAudioUrl && <audio className="voice-answer-player" src={spokenAudioUrl} controls preload="metadata" />}
          <footer>
            <button
              onClick={realtimeListening ? stopDictation : () => startDictation(true)}
              disabled={realtimePhase === "transcribing" || realtimePhase === "waiting" || realtimePhase === "speaking"}
            >
              {realtimeListening ? "结束并发送" : "开始说话"}
            </button>
            <button
              className="voice-send"
              disabled={!props.value.trim() || props.submitting}
              onClick={async () => {
                setRealtimePhase("waiting");
                await props.onSubmit();
              }}
            >
              发送文字并语音回答
            </button>
          </footer>
        </section>
        </>
      )}
    </div>
  );
}

function splitRealtimeSpeech(text: string, limit = 600) {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (!normalized) return [];
  const segments: string[] = [];
  let remaining = normalized;
  while (remaining.length > limit) {
    const candidate = remaining.slice(0, limit);
    const boundary = Math.max(
      candidate.lastIndexOf("。"),
      candidate.lastIndexOf("！"),
      candidate.lastIndexOf("？"),
      candidate.lastIndexOf("；")
    );
    const cut = boundary >= Math.floor(limit * 0.45) ? boundary + 1 : limit;
    segments.push(remaining.slice(0, cut));
    remaining = remaining.slice(cut).trim();
  }
  if (remaining) segments.push(remaining);
  return segments;
}

function voicePhaseLabel(
  phase: "idle" | "listening" | "transcribing" | "waiting" | "speaking" | "ready" | "error",
  ttsAvailable: boolean
) {
  if (phase === "listening") return "正在录音，结束后会自动发送";
  if (phase === "transcribing") return "正在通过服务端 ASR 转写";
  if (phase === "waiting") return "已发送，等待 Agent 回答";
  if (phase === "speaking") return "正在通过服务端 TTS 生成并播放";
  if (phase === "ready") return "回答已就绪，可阅读文字或手动播放";
  if (phase === "error") return "语音链路需要检查";
  return ttsAvailable ? "ASR 与 TTS 已接入" : "ASR 已接入；TTS 未配置时保留文字回答";
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
