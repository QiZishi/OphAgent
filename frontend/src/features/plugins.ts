import { FileText, Image, Stethoscope } from "lucide-react";
import type { PluginId } from "../types";

export const PLUGINS: Array<{
  id: PluginId;
  label: string;
  description: string;
  icon: typeof Image;
}> = [
  { id: "lesion_localizer", label: "病灶定位", description: "在原图标示经校验的可疑区域", icon: Image },
  { id: "aux_diagnosis", label: "辅助评估", description: "综合资料形成定性鉴别与下一步", icon: Stethoscope },
  { id: "report_generator", label: "报告生成", description: "生成可编辑、可导出的结构化报告", icon: FileText }
];

export const pluginLabel = (id: string) =>
  PLUGINS.find((item) => item.id === id)?.label
  || (["core", "interactive_vqa", "knowledge_base"].includes(id) ? "默认能力" : id);
