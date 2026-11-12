import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LanguageProvider } from "./app/language";
import App from "./app/App";
import { SessionProvider } from "./app/session";
import "./styles.css";
const client = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});
function Application() {
  const offlineDemo = useLocation().pathname === "/demo/offline";
  return (
    <SessionProvider offlineDemo={offlineDemo}>
      <LanguageProvider offlineDemo={offlineDemo}>
        <App />
      </LanguageProvider>
    </SessionProvider>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Application />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
