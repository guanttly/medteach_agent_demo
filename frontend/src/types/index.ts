export type SharkState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'working'
  | 'waiting_confirm'
  | 'success'
  | 'soft_warning'

export type StepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'fallback'

export interface WorkflowStep {
  id: string
  label: string
  status: StepStatus
}

export interface QuestionStructure {
  single_choice: number
  multiple_choice: number
  case_analysis: number
}

export interface ExamPlan {
  exam_name: string
  topic: string
  student_group: string
  student_count: number
  duration_minutes: number
  difficulty: string
  total_score: number
  grading: string
  question_structure: QuestionStructure
  question_total: number
}

export interface Student {
  id: string
  name: string
  department: string
  grade: string
  color: string
}

export interface Progress {
  label?: string
  published: number
  entered: number
  answering: number
  submitted: number
  remaining_seconds: number
}

export interface WeakPoint {
  name: string
  error_rate: number
  comment?: string
}

export interface ExamResult {
  exam_name?: string
  summary: {
    average: number
    highest: number
    lowest: number
    pass_rate: number
    submitted: number
    total: number
  }
  score_distribution: { range: string; count: number }[]
  students: { id: string; name: string; score: number; level: string }[]
  weak_points: WeakPoint[]
}

export interface CaseItem {
  id: string
  title: string
  focus: string
  difficulty: string
  tags: string[]
  est_minutes: number
}

export interface Recommendation {
  next_goal: string
  cases: CaseItem[]
}

export interface BusinessData {
  module: string
  title: string
  data: any
  fallback: boolean
}

export interface TickerEvent {
  id: number
  type: string
  title: string
  message: string
  status: string
  fallback: boolean
  ts: number
}

export interface WsEvent {
  type: string
  data: any
  event_id?: string
  session_id?: string
  turn_id?: string | null
  job_id?: string | null
  utterance_id?: string | null
  generation?: number
  priority?: string
  created_at?: number
}

export interface JobInfo {
  job_id: string
  type: string
  status: string
  current_step?: string | null
  progress_percent?: number
  progress_label?: string
}
