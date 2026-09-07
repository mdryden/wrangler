export interface Company {
  id: string
  name: string
  wave_equity_account_id: string
  wave_business_id?: string | null
  wave_access_token?: string | null
  wave_refresh_token?: string | null
  wave_token_expires_at?: string | null
  is_connected?: boolean
}

export interface CompanyCreatePayload {
  name: string
  wave_equity_account_id: string
  wave_business_id?: string | null
}

export interface CompanyUpdatePayload {
  name?: string
  wave_equity_account_id?: string
  wave_business_id?: string | null
  wave_access_token?: string | null
  wave_refresh_token?: string | null
  wave_token_expires_at?: string | null
}

export interface WaveCategory {
  id: string
  company_id: string
  wave_account_id: string
  name: string
}

export interface WaveAuthorizeResponse {
  authorization_url: string
  redirect_url: string
}

export type TokenStatus = "connected" | "disconnected" | "expired"

export interface TokenStatusInfo {
  status: TokenStatus
  label: string
  color: string
  textColor: string
  icon: string
  description: string
}

/**
 * Computes the token connection status for a company based on token presence and expiration.
 */
export function getCompanyTokenStatus(company: Partial<Company> | null | undefined): TokenStatus {
  if (!company || !company.wave_access_token) {
    return "disconnected"
  }

  if (company.wave_token_expires_at) {
    const expiresAt = new Date(company.wave_token_expires_at).getTime()
    if (!Number.isNaN(expiresAt) && expiresAt <= Date.now()) {
      return "expired"
    }
  }

  return "connected"
}

/**
 * Returns UI display metadata for a given token status.
 */
export function getTokenStatusInfo(status: TokenStatus): TokenStatusInfo {
  switch (status) {
    case "connected":
      return {
        status: "connected",
        label: "Connected",
        color: "positive",
        textColor: "white",
        icon: "check_circle",
        description: "Active Wave connection with valid access token",
      }
    case "expired":
      return {
        status: "expired",
        label: "Expired",
        color: "warning",
        textColor: "dark",
        icon: "warning",
        description: "Wave access token has expired and requires re-authorization or refresh",
      }
    case "disconnected":
    default:
      return {
        status: "disconnected",
        label: "Disconnected",
        color: "grey-6",
        textColor: "white",
        icon: "cloud_off",
        description: "No Wave account currently connected",
      }
  }
}
