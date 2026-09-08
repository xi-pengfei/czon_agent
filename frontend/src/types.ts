export type Identity = {
  username: string;
  role: string;
  is_admin: boolean;
  must_change_password: boolean;
  csrf_token: string;
};

export type Session = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type Attachment = {
  path: string;
  name: string;
  mime: string;
  size: number;
};

export type LocalDirectory = {
  name: string;
  entries: Array<{ relative_path: string; size: number }>;
  total_files: number;
  truncated: boolean;
};

export type Artifact = {
  id: string;
  name: string;
  mime: string;
  size: number;
  created_at: string;
  download_url: string;
};

export type Skill = { name: string; description: string };

export type Provider = {
  name: string;
  display_name: string;
  model: string;
  supports_vision: boolean;
  configured: boolean;
};

export type ToolStep = {
  type: string;
  id?: string;
  name: string;
  args?: Record<string, unknown>;
  result?: Record<string, unknown>;
  progress?: string;
  text?: string;
  duration_ms?: number;
};

export type RunMetrics = { duration_ms?: number; input_tokens?: number; output_tokens?: number };

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  attachments?: Attachment[];
  directory?: LocalDirectory;
  artifacts?: Artifact[];
  steps?: ToolStep[];
  state?: "running" | "done" | "stopped" | "error";
  metrics?: RunMetrics;
};

export type UserRecord = {
  username: string;
  role: string;
  active: boolean;
  must_change_password: boolean;
  created_at: string;
  last_login_at?: string;
  department_id?: string | null;
  department_name?: string | null;
  monthly_token_quota_million?: number | null;
  effective_token_quota_million?: number | null;
  usage_tokens?: number;
};

export type DepartmentRecord = {
  id: string;
  name: string;
  parent_id: string | null;
  monthly_token_quota_million: number | null;
  active: boolean;
  user_count: number;
  created_at: string;
};

export type RoleRecord = {
  name: string;
  skills: "*" | string[];
  tools: "*" | string[];
  models: "*" | string[];
  is_admin: boolean;
};

export type ModelRecord = {
  name: string;
  display_name: string;
  base_url: string;
  model: string;
  api_key_configured?: boolean;
  supports_vision: boolean;
  supports_tools: boolean;
  supports_streaming: boolean;
  enabled: boolean;
};

export type AuditRecord = {
  actor: string;
  action: string;
  target: string;
  created_at: string;
};

export type RuntimeLog = {
  timestamp: string;
  level: string;
  message: string;
};
