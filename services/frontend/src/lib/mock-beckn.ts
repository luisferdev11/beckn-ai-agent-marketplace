import { MOCK_RESULTS } from './mock-data';

export type BecknStepId =
  | 'select'
  | 'on_select'
  | 'init'
  | 'on_init'
  | 'confirm'
  | 'executing'
  | 'on_status';

export type StepStatus = 'pending' | 'active' | 'done' | 'error';

export interface BecknStep {
  id: BecknStepId;
  label: string;
  description: string;
  status: StepStatus;
  timestamp?: string;
}

export interface FlowState {
  transactionId: string;
  agentId: string;
  agentName: string;
  agentIcon: string;
  steps: BecknStep[];
  result?: object;
  completed: boolean;
  startedAt: string;
}

export const BECKN_STEPS: Omit<BecknStep, 'status' | 'timestamp'>[] = [
  { id: 'select',     label: 'select',    description: 'BAP → select agent on network' },
  { id: 'on_select',  label: 'on_select', description: 'BPP ← price & terms confirmed' },
  { id: 'init',       label: 'init',      description: 'BAP → provide fulfillment details' },
  { id: 'on_init',    label: 'on_init',   description: 'BPP ← contract terms acknowledged' },
  { id: 'confirm',    label: 'confirm',   description: 'BAP → confirm & fund settlement' },
  { id: 'executing',  label: 'executing', description: 'Agent processing your task…' },
  { id: 'on_status',  label: 'on_status', description: 'BPP ← execution result delivered' },
];

const STEP_DELAYS: Record<BecknStepId, number> = {
  select:     700,
  on_select:  1100,
  init:       500,
  on_init:    700,
  confirm:    500,
  executing:  2800,
  on_status:  600,
};

function nowIso() {
  return new Date().toISOString();
}

function uuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function sleep(ms: number) {
  return new Promise<void>(resolve => setTimeout(resolve, ms));
}

export function getFlowState(transactionId: string): FlowState | null {
  if (typeof window === 'undefined') return null;
  const raw = sessionStorage.getItem(`beckn:${transactionId}`);
  return raw ? JSON.parse(raw) : null;
}

function saveFlowState(state: FlowState) {
  if (typeof window === 'undefined') return;
  sessionStorage.setItem(`beckn:${state.transactionId}`, JSON.stringify(state));
}

export async function* runBecknFlow(
  agentId: string,
  agentName: string,
  agentIcon: string,
  _input: string,
): AsyncGenerator<FlowState> {
  const transactionId = uuid();

  const state: FlowState = {
    transactionId,
    agentId,
    agentName,
    agentIcon,
    steps: BECKN_STEPS.map(s => ({ ...s, status: 'pending' as StepStatus })),
    completed: false,
    startedAt: nowIso(),
  };
  saveFlowState(state);
  yield { ...state };

  for (let i = 0; i < state.steps.length; i++) {
    const stepId = state.steps[i].id;

    // Mark current step active
    state.steps = state.steps.map((s, idx) =>
      idx === i ? { ...s, status: 'active' } : s,
    );
    saveFlowState(state);
    yield { ...state };

    await sleep(STEP_DELAYS[stepId]);

    // Mark done
    state.steps = state.steps.map((s, idx) =>
      idx === i ? { ...s, status: 'done', timestamp: nowIso() } : s,
    );

    // Attach result on final step
    if (stepId === 'on_status') {
      state.result = MOCK_RESULTS[agentId] ?? { message: 'Agent execution complete.' };
      state.completed = true;
    }

    saveFlowState(state);
    yield { ...state };
  }
}
