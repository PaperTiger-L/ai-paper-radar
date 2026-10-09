/* 与后端 API 契约一致的类型定义 */

export interface Subscriber {
  id: number;
  name: string;
  email: string;
  field: string;
  research_problem: string;
  methods: string;
  keywords: string[];
  venues: string[];
  papers_per_week: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface DashboardData {
  subscriber_count: number;
  active_subscriber_count: number;
  papers_7d: number;
  recommendations_7d: number;
  last_run: RunInfo | null;
  next_run_at: string | null;
  recent_runs: RunInfo[];
  llm_configured: boolean;
  smtp_configured: boolean;
  schedule_enabled: boolean;
}

export interface RunInfo {
  id: number;
  subscriber_id: number;
  subscriber_name: string;
  week_start: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  papers_found: number;
  papers_selected: number;
  email_status: string;
  email_error: string | null;
}

export interface Paper {
  id: number;
  title: string;
  zh_title: string;
  authors: string[];
  venue: string;
  published_date: string;
  url: string;
  source: string;
  is_preprint: boolean;
  abstract: string;
  zh_abstract: string;
  innovations: string[];
  recommend_reason: string;
  relevance_score: number;
  subscriber_id: number;
  subscriber_name: string;
  run_id: number;
}

export interface PaperList {
  total: number;
  items: Paper[];
}

export interface LlmConfig {
  provider: string;
  base_url: string;
  model: string;
  has_api_key: boolean;
  api_key_preview: string;
  updated_at: string | null;
}

export interface SmtpConfig {
  host: string;
  port: number;
  username: string;
  from_email: string;
  from_name: string;
  use_tls: boolean;
  use_ssl: boolean;
  has_password: boolean;
  password_preview: string;
}

export interface ScheduleConfig {
  enabled: boolean;
  day_of_week: number; // 0=周一 .. 6=周日
  hour: number;
  minute: number;
  timezone: string;
}

export interface JobStatus {
  job_id: string;
  status: string; // pending | running | done | failed
  progress: number; // 0-100
  message: string;
}

export interface LogItem {
  id: number;
  ts: string;
  category: string;
  level: string;
  message: string;
}

export interface DigestPreview {
  subject: string;
  html: string;
  run_id: number;
}

export interface VenueLists {
  conferences: string[];
  journals: string[];
}

export interface PageResult<T> {
  total: number;
  items: T[];
}
