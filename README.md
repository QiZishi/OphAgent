<p align="center">
  <img src="figures/模型图标.png" width="120" alt="OphVLM-R1 project icon">
</p>

<h1 align="center">OphAgent · “LingTong” Ophthalmic Intelligent Diagnosis System</h1>

<p align="center"><strong>A ReAct-based ophthalmic multimodal reasoning and clinical assistance platform</strong></p>

<p align="center">
  <a href="README.md">English</a> · <a href="README_zh.md">简体中文</a>
</p>

<p align="center">
  <a href="https://qizishi.github.io/OphVLM-R1/"><img src="https://img.shields.io/badge/Project-Page-2b6cb0?style=for-the-badge" alt="Project page"></a>
  <a href="https://github.com/QiZishi/OphAgent/"><img src="https://img.shields.io/badge/Code-OphAgent-181717?style=for-the-badge&logo=github" alt="OphAgent code"></a>
</p>
<p align="center">
  <a href="https://huggingface.co/QiZishi/OphVLM-R1"><img src="https://img.shields.io/badge/🤗%20Model-Hugging%20Face-FFD21E?style=for-the-badge" alt="Model on Hugging Face"></a>
  <a href="https://www.modelscope.cn/models/MoonNight/OphVLM-R1"><img src="https://img.shields.io/badge/Model-ModelScope-624AFF?style=for-the-badge" alt="Model on ModelScope"></a>
</p>
<p align="center">
  <a href="https://huggingface.co/datasets/QiZishi/OphReason-Vision"><img src="https://img.shields.io/badge/🤗%20Dataset-Hugging%20Face-FFD21E?style=for-the-badge" alt="Dataset on Hugging Face"></a>
  <a href="https://www.modelscope.cn/datasets/MoonNight/OphReason-Vision"><img src="https://img.shields.io/badge/Dataset-ModelScope-624AFF?style=for-the-badge" alt="Dataset on ModelScope"></a>
</p>

## Project Links

- **Project page**: <https://qizishi.github.io/OphVLM-R1/>
- **OphAgent system code**: [GitHub](https://github.com/QiZishi/OphAgent/)
- **OphVLM-R1 model**: [Hugging Face](https://huggingface.co/QiZishi/OphVLM-R1) | [ModelScope](https://www.modelscope.cn/models/MoonNight/OphVLM-R1)
- **OphReason-Vision dataset**: [Hugging Face](https://huggingface.co/datasets/QiZishi/OphReason-Vision) | [ModelScope](https://www.modelscope.cn/datasets/MoonNight/OphReason-Vision)

## News

- **2026.07.07** 🎉 Paper “OphVLM-R1: Efficient Ophthalmic Reasoning via Curriculum Reinforcement Learning” accepted by **WAICA 2026**!
  - 📖 Conference: <https://waica2026.worldaic.com.cn/>

- **2025.12.09** 🎉 **Exciting News!** The “LingTong” Ophthalmic Intelligent Diagnosis System has been featured and promoted by Shanghai AI Laboratory and awarded the **Outstanding Project of InternLM Practical Camp**!
  - 📖 Featured Article: <https://mp.weixin.qq.com/s/BTZPUrVtD8nCS_yMwDhhUQ>

- **2025.11.28** 📊 The high-quality ophthalmic multimodal reasoning dataset **OphReason-Vision** subset has been officially open-sourced on the ModelScope platform!
  - 🔗 Dataset Link: <https://www.modelscope.cn/datasets/MoonNight/OphReason-Vision>

- **2025.11.23** 🎬 The “LingTong” Ophthalmic Intelligent Diagnosis System demo video has been officially released on Bilibili, showcasing the full-process diagnostic capabilities of all five intelligent agents!
  - 🎥 Video Link: <https://www.bilibili.com/video/BV1g4UTBZEEm/>

## Background

**“LingTong” Ophthalmic Intelligent Diagnosis System** is a specialized medical AI platform built upon the self-developed **OphVLM-R1 ophthalmic multimodal reasoning model**. Developed by the AI Safety Laboratory team at the School of Artificial Intelligence and Automation, Huazhong University of Science and Technology, the project aims to address the global disparity in high-quality ophthalmic medical resources and the high rates of misdiagnosis and missed diagnosis in primary medical institutions.

Ophthalmic multimodal large language models face three challenges: training data lacking structured reasoning chains, single-stage training that fails to cultivate deep clinical reasoning, and large model sizes that limit deployment in resource-constrained settings. The project addresses these challenges through an integrated data–model–agent stack. OphReason-Vision converts heterogeneous ophthalmic data into expert-verified reasoning trajectories; OphVLM-R1 develops clinical reasoning through a LoRA cold start followed by curriculum reinforcement learning; and OphAgent exposes the resulting capabilities through a modular clinical-assistance system.

Based on the InternLM ecosystem, including InternVL3.5 and Intern-S1, the system adopts a **ReAct (Reasoning + Acting) agent architecture** and integrates five professional AI agents: Interactive VQA, Lesion Localization, Diagnostic Assistant, Report Generation, and Ophthalmic Knowledge Base. Through the dataset construction pipeline, two-stage model training, and the ReAct agent system, LingTong advances ophthalmic intelligent diagnosis from “perceptual recognition” toward “cognitive reasoning” while keeping intermediate actions inspectable and traceable.

**Core objective:** empower clinicians, especially primary healthcare workers, with AI-assisted early screening and precise diagnosis capabilities for ophthalmic diseases. LingTong is a research and clinical-assistance system and is not a substitute for professional medical judgment.

## OphReason-Vision Dataset Pipeline

The three-stage closed loop transforms 100K+ raw clinical cases and 30+ public datasets into 15,418 reasoning trajectories.

![OphReason-Vision data pipeline](figures/data_pipeline.png)

### 1. Data Standardization

This stage integrates 100K+ clinical cases with 30+ public datasets through a dual-stream strategy. The **text stream** parses unstructured electronic medical records into standardized JSON and resolves inconsistent terminology through a curated ophthalmic synonym table. The **visual stream** generates detailed textual descriptions for datasets that contain only image-level labels, enriching the visual evidence available for subsequent reasoning synthesis.

### 2. Structured Reasoning Synthesis

Intern-S1 generates multidimensional instructions covering lesion localization, multimodal diagnosis, and knowledge question answering. For each instruction, it produces a Chain-of-Thought trajectory that follows the clinical diagnostic workflow:

> visual sign identification → knowledge retrieval → pathological analysis → clinical decision

An LVLM-as-a-Judge filter uses Intern-S1 with threshold $\tau=0.7$, determined on 500 expert-reviewed pilot samples to maximize F1. It evaluates medical correctness, reasoning consistency, step completeness, and clarity, while flagging hallucinated findings, incorrect disease classification, and logically inconsistent steps.

### 3. Expert-Collaborative Optimization

Three board-certified ophthalmologists review the 18% of samples flagged as difficult. Inter-rater agreement reaches Cohen's $\kappa=0.82$, and disagreements are discussed until consensus. Difficulty is graded from base-model perplexity so that the curriculum can progress from easier perception tasks to harder long-form reasoning tasks. Perceptual hashing, source-identifier cross-referencing, and manual source audits are used to reduce contamination with external benchmarks.

| Split | Records | Purpose |
|---|---:|---|
| Cold-start SFT | 3,418 | Domain knowledge injection |
| Four curriculum stages | 10,000 | Progressive reasoning training |
| In-domain evaluation | 2,000 | Held-out clinical evaluation |
| **Total** | **15,418** | **13,418 train + 2,000 eval** |

## OphVLM-R1 Training Framework and Algorithms

OphVLM-R1 is a 2B-parameter model based on InternVL3.5-2B. Its lightweight scale supports deployment on consumer-grade GPUs while retaining capacity for multimodal clinical reasoning. Training proceeds in two stages: parameter-efficient supervised fine-tuning injects ophthalmic knowledge, followed by curriculum reinforcement learning that progressively develops diagnostic reasoning.

![OphVLM-R1 two-stage training framework](figures/two_stage_training.png)

### Stage 1: LoRA Supervised Fine-Tuning

The 3,418-sample cold-start subset injects broad ophthalmic domain knowledge with Low-Rank Adaptation (LoRA), constraining weight updates to low-rank decomposition. The adapters use rank $r=64$ and scaling $\alpha=128$ on the $W_q$, $W_k$, $W_v$, and $W_o$ attention projections. Training uses cosine annealing from a learning rate of $1\times10^{-4}$, batch size 32, and 3 epochs; approximately 0.5% of the total parameters are trainable.

### Stage 2: Curriculum Reinforcement Learning

Four tasks are ordered by increasing diagnostic complexity:

1. Lesion Localization.
2. Multi-image Selection.
3. Report Generation.
4. Knowledge Q&A.

Group Sequence-level Policy Optimization (GSPO) addresses instability from token-level policy ratios in long reasoning chains by computing importance ratios at sequence level. Each curriculum stage optimizes a mixed reward combining rule-based verifiable reward and an Intern-S1-mini judge reward, with weights $\lambda_1=0.6$ and $\lambda_2=0.4$. Training uses $G=8$, $\varepsilon=0.2$, learning rate $5\times10^{-6}$, $\beta_{\mathrm{KL}}=0.04$, and 2 epochs per stage.

### Hard-Sample Dynamic Backtracking

An on-policy resampling mechanism tracks prompts whose rewards remain below a threshold over the most recent $k=5$ rounds and increases their sampling probability according to consecutive failure counts. It stores only prompt indices and failure statistics, ensuring fresh on-policy rollouts whenever a difficult prompt is revisited. Resampling is capped at 30% of each batch to retain coverage of already learned samples.

## Model Performance

Accuracy is reported in percent. The average is reference-only because the benchmarks use different formats, difficulties, and random baselines.

| Model | In-Domain | Fundus | Omni-Eye | Avg.* |
|---|---:|---:|---:|---:|
| InternVL3.5-2B | 34.50 | 36.61 | 55.47 | 42.19 |
| InternVL3.5-4B | 36.23 | 42.10 | 77.51 | 51.95 |
| Lingshu-7B | **44.20** | 41.29 | 87.42 | **57.64** |
| OphthaReason-Qwen-3B | 36.60 | 38.87 | 86.86 | 54.11 |
| **OphVLM-R1-2B (ours)** | 38.40 | 42.58 | **88.24** | 56.41 |

Within the reported comparisons, OphVLM-R1 achieves 88.24% on out-of-domain OmniMedVQA-Eye and 42.58% on Fundus-MMBench. Its 56.41% reference average exceeds InternVL3.5-4B at 51.95% and the domain-adapted OphthaReason-Qwen-3B at 54.11%. Ablations reduce Omni-Eye by 26.21 points with SFT only, 10.10 points with one-shot RL, 3.72 points when GSPO is replaced by token-level GRPO, and 2.12 points without hard-sample backtracking. Results are single runs without confidence intervals or significance tests, and comparisons with off-the-shelf 7B/8B models should be interpreted cautiously because training-data exposure and model scale are not controlled.

## OphAgent Design Architecture

The LingTong system is built on a ReAct architecture, implementing a closed loop of **Reasoning → Acting → Observation**. Each agent first analyzes the clinical request and available multimodal evidence, then selects and executes the appropriate action before incorporating the returned observation. This design keeps task decomposition, tool execution, and returned evidence inspectable and traceable.

```text
OphAgent/
├── app/
│   ├── main.py              # FastAPI application
│   ├── agents/              # ReAct agents
│   ├── api/                 # API routes
│   ├── services/            # Business services
│   └── static/              # Web interface
├── figures/                 # Documentation assets
├── requirements.txt
└── run.py
```

- **Backend**: built with FastAPI for asynchronous processing and automatic API documentation; SQLModel unifies data validation and database models, while SQLite provides lightweight persistence.
- **Frontend**: developed with native JavaScript ES6+ without a framework dependency, with responsive layouts for desktop and mobile devices.
- **Communication**: WebSocket integration supports real-time communication and streaming model responses.
- **Agent layer**: five modular agents follow the ReAct workflow and map directly to distinct clinical-assistance tasks.

## Core Highlights

- **🧠 OphVLM-R1 driven**: a lightweight 2B-parameter ophthalmic reasoning model supports fundus photographs, OCT, and anterior-segment images.
- **🔄 ReAct architecture**: each agent separates reasoning from action, making intermediate decisions easier to inspect than a single opaque model response.
- **🎯 Five professional agents**: the system covers image interaction, lesion analysis, candidate diagnosis, report writing, and knowledge inquiry.
- **💡 Modularity and interpretability**: clinical capabilities are separated into focused components that can be configured, maintained, and extended independently.

## Core Functions

### Interactive VQA

Supports uploading ophthalmic images for free-form question answering and multi-turn follow-ups, allowing users to refine questions as new findings emerge.

![Interactive VQA demo](figures/demo_interactive_vqa.png)

### Lesion Localization

Automatically identifies and annotates suspected lesion regions in ophthalmic images and returns standardized bounding boxes for downstream inspection.

![Lesion localization demo](figures/demo_lesion_localization.png)

### Diagnostic Assistant

Provides multiple candidate diagnoses with confidence information and supporting diagnostic evidence to assist clinical review.

![Diagnostic assistant demo](figures/demo_aux_diagnosis.png)

### Report Generation

Automatically generates structured ophthalmic imaging reports containing imaging findings and diagnostic impressions.

![Report generation demo](figures/demo_report_generation.png)

### Ophthalmic Knowledge Base

Provides professional ophthalmic medical knowledge question answering and returns supporting sources when the retrieval service is configured.

![Knowledge base demo](figures/demo_knowledge_base.png)

## Quick Start

### Environment Requirements

- Python 3.8+
- 8 GB+ RAM recommended
- GPU support optional for local model deployment

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/QiZishi/OphAgent.git
   cd OphAgent
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:

   ```bash
   cp .env.example .env
   # Edit .env to configure the model service.
   ```

4. Initialize the database and start the system:

   ```bash
   python init_db.py
   python run.py
   ```

5. Open <http://localhost:8012>, register an account, and start using the system.

## Development

### Adding a New Agent

1. Create the agent module under `app/agents/`.
2. Register its API route under `app/api/`.
3. Add the corresponding frontend module under `app/static/js/agents/`.

Deployment-specific settings are managed in `app/core/config.py` and `.env`.

## FAQ

1. **Model service connection failure**
   - Check `OPENAI_API_BASE` and related credentials in `.env`.
   - Confirm that the configured model service is running and reachable.
2. **File upload issues**
   - Check permissions for `app/static/uploads/`.
3. **Database issues**
   - Run `python init_db.py` to initialize the local database again.

## Open Source Status

### Available

- **System code**: frontend/backend implementation, API routes, services, and database models.
- **OphReason-Vision subset**: 3,418 cold-start samples on Hugging Face and ModelScope.
- **OphVLM-R1 model**: model weights on Hugging Face and ModelScope.

### Planned Releases

- Remaining OphReason-Vision records after completion of privacy and ethics review.
- Cold-start SFT and curriculum reinforcement learning scripts.
- Model evaluation code.

## Citation

```bibtex
@inproceedings{qi2026ophvlm,
  title={OphVLM-R1: Efficient Ophthalmic Reasoning via Curriculum Reinforcement Learning},
  author={Qi, Zishi and Hu, Xiaoya and Pan, Huilin and Gao, Ang and Hou, Jiaxin and Li, Jiankun and Qian, Yongao},
  booktitle={Proceedings of the World Artificial Intelligence Conference Academic (WAICA)},
  year={2026}
}
```

## Acknowledgements

The development of this project benefits from the InternLM ecosystem, OpenGVLab, the InternLM Practical Camp, and the Datawhale open-source community. We sincerely thank these communities for providing the model, tooling, and learning resources that support the project, and we thank the ophthalmologists who contributed to data review and quality assurance.

## Related Links

- **InternVL**: <https://github.com/OpenGVLab/InternVL>
- **InternLM online experience**: <https://chat.intern-ai.org.cn/>
- **InternLM Practical Camp**: <https://colearn.intern-ai.org.cn/go>
- **Datawhale**: <https://www.datawhale.cn/>
