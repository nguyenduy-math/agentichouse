import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export interface ChunkSource {
  chunk_id: string;
  source_file: string;
  page_number: number;
  chunk_index: number;
  excerpt: string;
  rerank_score: number;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  rewritten_query: string;
  domains_used: string[];
  is_out_of_scope: boolean;
  sources: ChunkSource[];
}

export const createSession = async (): Promise<string> => {
  const res = await api.post<{ session_id: string }>("/session");
  return res.data.session_id;
};

export const sendMessage = async (
  session_id: string,
  message: string
): Promise<ChatResponse> => {
  const res = await api.post<ChatResponse>("/chat", { session_id, message });
  return res.data;
};

export const uploadDocument = async (
  file: File,
  domain: string
): Promise<{ chunks_created: number; domain: string }> => {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post<{ chunks_created: number; domain: string }>(
    `/admin/ingest?domain=${domain}`,
    form
  );
  return res.data;
};

export const getDomains = async (): Promise<Record<string, string>> => {
  const res = await api.get<Record<string, string>>("/admin/domains");
  return res.data;
};

export const getStats = async (): Promise<{ total_chunks: number; bm25_corpus_size: number }> => {
  const res = await api.get("/admin/stats");
  return res.data;
};
