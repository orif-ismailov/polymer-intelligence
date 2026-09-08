export interface Account {
  id: number;
  phone: string;
  /** Staff-issued sign-in name. `null` until credentials are issued. */
  login: string | null;
  name: string | null;
  language: string;
  status: string;
  /**
   * The issued password is printed in a contract, so it is an initial secret and
   * nothing more. While this is true the API answers 403 `password_change_required`
   * on every guarded route, and `RequirePasswordCurrent` keeps the UI off them.
   */
  must_change_password: boolean;
}

export interface AuthResult {
  access_token: string;
  token_type: "bearer";
  account: Account;
}

export interface LoginPayload {
  login: string;
  password: string;
}

/** An access REQUEST. It grants nothing — staff issue credentials afterwards. */
export interface RegisterPayload {
  contact_name: string;
  phone: string;
  company_name: string;
  note?: string;
}

export interface PasswordChangePayload {
  current_password: string;
  new_password: string;
}

export interface AccountPatch {
  name?: string;
  language?: string;
}
