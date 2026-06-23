export type UserRole = 'admin' | 'approver' | 'viewer';

export type AccountStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'inactive'
  | 'pending_email'
  | 'pending_email_change';

export interface UserMe {
  id: number;
  username: string;
  email: string | null;
  role: UserRole;
  account_status: AccountStatus;
  is_active: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface PendingUser {
  id: number;
  username: string;
  email: string | null;
  requested_role: string | null;
  approvals_count: number;
}
