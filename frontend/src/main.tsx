import React, { lazy, Suspense, useEffect } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Routes,
  Route,
  Link,
  useLocation,
} from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PlatformProvider } from "./data/Platform";
import { Layout } from "./components/Layout";
const Dashboard = lazy(() =>
  import("./pages/Dashboard").then((module) => ({ default: module.Dashboard })),
);
const Trends = lazy(() =>
  import("./pages/Trends").then((module) => ({ default: module.Trends })),
);
const Cameras = lazy(() =>
  import("./pages/Cameras").then((module) => ({ default: module.Cameras })),
);
const Control = lazy(() =>
  import("./pages/Control").then((module) => ({ default: module.Control })),
);
const Alarms = lazy(() =>
  import("./pages/Records").then((module) => ({ default: module.Alarms })),
);
const Logs = lazy(() =>
  import("./pages/Records").then((module) => ({ default: module.Logs })),
);
const AI = lazy(() =>
  import("./pages/AI").then((module) => ({ default: module.AI })),
);
const Settings = lazy(() =>
  import("./pages/Settings").then((module) => ({ default: module.Settings })),
);
import { ErrorBoundary } from "./components/ErrorBoundary";
import "./styles.css";
document.documentElement.dataset.density =
  localStorage.getItem("platform.density") || "comfortable";
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <PlatformProvider>
          <BrowserRouter>
            <ScrollReset />
            <Suspense
              fallback={
                <div className="loading" role="status">
                  正在加载页面…
                </div>
              }
            >
              <Routes>
                <Route element={<Layout />}>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/trends" element={<Trends />} />
                  <Route path="/cameras" element={<Cameras />} />
                  <Route path="/control" element={<Control />} />
                  <Route path="/alarms" element={<Alarms />} />
                  <Route path="/logs" element={<Logs />} />
                  <Route path="/ai" element={<AI />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route
                    path="*"
                    element={
                      <div className="page empty">
                        <h1>页面不存在</h1>
                        <Link to="/">返回总览</Link>
                      </div>
                    }
                  />
                </Route>
              </Routes>
            </Suspense>
          </BrowserRouter>
        </PlatformProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);

function ScrollReset() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}
