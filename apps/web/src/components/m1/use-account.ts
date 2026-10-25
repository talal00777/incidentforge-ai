"use client";

import { useEffect, useState } from "react";
import { Account, ApiError, apiGet, describeApiFailure } from "@/lib/api-client";

type AccountState =
  | { state: "loading" }
  | { state: "signed-out" }
  | { state: "error"; message: string }
  | { state: "signed-in"; user: Account };

export function useAccount(): AccountState {
  const [account, setAccount] = useState<AccountState>({ state: "loading" });

  useEffect(() => {
    let active = true;
    apiGet<Account>("auth/me")
      .then((user) => { if (active) setAccount({ state: "signed-in", user }); })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          setAccount({ state: "signed-out" });
        } else {
          setAccount({ state: "error", message: describeApiFailure(error) });
        }
      });
    return () => { active = false; };
  }, []);
  return account;
}
