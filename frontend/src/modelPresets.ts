export type ModelPreset = {
  id: string;
  label: string;
  shortLabel: string;
  description: string;
  base_url: string;
  help_url: string;
  help_label: string;
  vision: boolean;
  tools: boolean;
  streaming: boolean;
  apiKey?: string;
};

export const modelPresets: ModelPreset[] = [
  {
    id: "deepseek",
    label: "DeepSeek",
    shortLabel: "DeepSeek",
    description: "国内云模型，适合文本推理与工具调用",
    base_url: "https://api.deepseek.com/v1",
    help_url: "https://platform.deepseek.com/api_keys",
    help_label: "前往 DeepSeek 创建 API Key",
    vision: false,
    tools: true,
    streaming: true,
  },
  {
    id: "kimi",
    label: "Moonshot / Kimi",
    shortLabel: "Kimi",
    description: "国内云模型，适合长文本和日常办公",
    base_url: "https://api.moonshot.cn/v1",
    help_url: "https://platform.moonshot.cn/console/api-keys",
    help_label: "前往 Kimi 开放平台创建 API Key",
    vision: true,
    tools: true,
    streaming: true,
  },
  {
    id: "qwen",
    label: "阿里云 / 通义千问",
    shortLabel: "通义千问",
    description: "阿里云百炼模型，覆盖文本与多模态",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    help_url: "https://bailian.console.aliyun.com/",
    help_label: "前往阿里云百炼创建 API Key",
    vision: true,
    tools: true,
    streaming: true,
  },
  {
    id: "ollama",
    label: "Ollama（本机私有模型）",
    shortLabel: "Ollama",
    description: "模型运行在本机或内网服务器，数据不发送到公有云",
    base_url: "http://127.0.0.1:11434/v1",
    help_url: "https://ollama.com/download",
    help_label: "下载并安装 Ollama",
    vision: false,
    tools: true,
    streaming: true,
    apiKey: "ollama",
  },
];
