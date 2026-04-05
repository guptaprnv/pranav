/**
 * Global state store — Zustand
 * Polls the node agent and caches status for all screens.
 */
import { create } from 'zustand';
import axios from 'axios';

export interface AgentStatus {
  peer_id: string;
  owner: string;
  device_type: string;
  hardware_tier: string;
  peers_known: number;
  gossip_round: number;
  session_id: string | null;
  total_compute_units: number;
  running: boolean;
}

export interface CreditBalance {
  owner: string;
  available: number;
  lifetime_earned: number;
  lifetime_spent: number;
}

interface AgentStore {
  agentUrl: string;
  sessionId: string | null;
  status: AgentStatus | null;
  credits: CreditBalance | null;
  peers: any[];
  error: string | null;
  setAgentUrl: (url: string) => void;
  fetchStatus: () => Promise<void>;
  startContributing: () => Promise<void>;
  stopContributing: () => Promise<void>;
}

export const useAgentStore = create<AgentStore>((set, get) => ({
  agentUrl: 'http://127.0.0.1:7777',   // default: local agent
  sessionId: null,
  status: null,
  credits: null,
  peers: [],
  error: null,

  setAgentUrl: (url) => set({ agentUrl: url }),

  fetchStatus: async () => {
    const { agentUrl } = get();
    try {
      const [statusRes, creditsRes, peersRes] = await Promise.all([
        axios.get(`${agentUrl}/status`, { timeout: 3000 }),
        axios.get(`${agentUrl}/credits`, { timeout: 3000 }),
        axios.get(`${agentUrl}/peers`, { timeout: 3000 }),
      ]);
      set({
        status: statusRes.data,
        credits: creditsRes.data,
        peers: peersRes.data,
        sessionId: statusRes.data.session_id,
        error: null,
      });
    } catch (e: any) {
      set({ error: e.message || 'Agent unreachable' });
    }
  },

  startContributing: async () => {
    // On iPad, "contributing" means keeping the app alive and processing
    // inference/validation tasks (training runs on Mac mini / cloud).
    // TODO: integrate with Core ML for on-device inference contribution
    await get().fetchStatus();
  },

  stopContributing: async () => {
    const { agentUrl } = get();
    try {
      await axios.post(`${agentUrl}/stop`, {}, { timeout: 3000 });
    } catch { /* agent may already be stopped */ }
    await get().fetchStatus();
  },
}));
