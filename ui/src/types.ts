export const API = 'http://localhost:8000/api';

export interface Health {
  db: { ok: boolean; error: string };
  llm: { ok: boolean; error: string };
  telegram: { ok: boolean; error: string; bot_name: string };
}

export interface Memory {
  id: string;
  source_type: string;
  content: string;
  created_at: string;
  metadata: any;
}

export interface LogEntry {
  level: string;
  source: string;
  message: string;
  timestamp: string;
}

export interface Config {
  telegramToken: string;
  llmApiKey: string;
  dbPassword: string;
  dbUser: string;
  dbName: string;
  dbHost: string;
  llmBaseUrl: string;
  modelText: string;
  modelReasoning: string;
  modelCoding: string;
  modelVision: string;
  modelEmbedding: string;
  sttProvider: string;
  openaiApiKey: string;
  groqApiKey: string;
  whisperModelSize: string;
}

export type Tab = 'dashboard' | 'chat' | 'ingest' | 'settings' | 'logs';

export const EMPTY_CONFIG: Config = {
  telegramToken: '',
  llmApiKey: '',
  dbPassword: '',
  dbUser: '',
  dbName: '',
  dbHost: '',
  llmBaseUrl: '',
  modelText: '',
  modelReasoning: '',
  modelCoding: '',
  modelVision: '',
  modelEmbedding: '',
  sttProvider: 'openai',
  openaiApiKey: '',
  groqApiKey: '',
  whisperModelSize: 'base',
};
