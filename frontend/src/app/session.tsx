import { createContext, useContext } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, post, setCsrf } from "../lib/api";
import type { User } from "../lib/types";
const Session = createContext<{
  user: User | null | undefined;
  loading: boolean;
  refresh: () => Promise<User | null>;
  clear: () => Promise<void>;
  ensure: () => Promise<User>;
}>({
  user: null,
  loading: false,
  refresh: async () => null,
  clear: async () => {},
  ensure: async () => {
    throw Error("Session unavailable");
  },
});
async function readProfile() {
  try {
    const user = await api<User>("/me");
    setCsrf(user.csrf_token);
    return { ...user, guest: user.is_guest };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      setCsrf("");
      return null;
    }
    throw error;
  }
}
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["me"],
    queryFn: readProfile,
    retry: false,
  });
  async function refresh() {
    const previous = qc.getQueryData<User | null>(["me"]);
    const next = await readProfile();
    if (previous?.id !== next?.id) {
      // Private source and analysis caches must not survive an account switch.
      const privateQueries = {
        predicate: (q: { queryKey: readonly unknown[] }) =>
          q.queryKey[0] !== "me",
      };
      await qc.cancelQueries(privateQueries);
      qc.removeQueries(privateQueries);
    }
    qc.setQueryData(["me"], next);
    return next;
  }
  async function clear() {
    await qc.cancelQueries();
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    setCsrf("");
    qc.setQueryData(["me"], null);
  }
  async function ensure() {
    const current = qc.getQueryData<User | null>(["me"]);
    if (current) return current;
    await post("/auth/guest");
    const raw = await api<User>("/me");
    const u = { ...raw, guest: raw.is_guest };
    setCsrf(u.csrf_token);
    qc.setQueryData(["me"], u);
    return u;
  }
  return (
    <Session.Provider
      value={{
        user: query.data,
        loading: query.isPending,
        refresh,
        clear,
        ensure,
      }}
    >
      {children}
    </Session.Provider>
  );
}
export const useSession = () => useContext(Session);
