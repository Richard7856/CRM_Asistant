/**
 * Auth API — login, register, refresh, and profile endpoints.
 * Kept separate from the main apiClient so we can call login/register
 * before the auth interceptor is wired up.
 */

import apiClient from "./client";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  role: "owner" | "admin" | "member" | "viewer";
  is_active: boolean;
  organization_id: string;
  organization_name: string | null;
  created_at: string;
}

export async function loginApi(email: string, password: string): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/auth/login", { email, password });
  return data;
}

export async function registerApi(
  email: string,
  password: string,
  full_name: string,
  org_name: string,
): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/auth/register", {
    email,
    password,
    full_name,
    org_name,
  });
  return data;
}

export async function refreshApi(refresh_token: string): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/auth/refresh", { refresh_token });
  return data;
}

export async function getMeApi(): Promise<UserProfile> {
  const { data } = await apiClient.get<UserProfile>("/auth/me");
  return data;
}
