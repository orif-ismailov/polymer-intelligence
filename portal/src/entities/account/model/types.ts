export interface Account {
  id: number;
  phone: string;
  name: string | null;
  language: string;
  status: string;
}

export interface AuthResult {
  access_token: string;
  token_type: "bearer";
  account: Account;
}

export interface OtpRequestPayload {
  phone: string;
}

export interface OtpVerifyPayload {
  phone: string;
  code: string;
}

export interface AccountPatch {
  name?: string;
  language?: string;
}
