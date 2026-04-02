type AdminRuntimeConfigKey = "VITE_API_BASE_URL";

type RuntimeConfigStore = Partial<Record<AdminRuntimeConfigKey, string>>;

const runtimeConfigGlobal = globalThis as typeof globalThis & {
  __REMNASTORE_RUNTIME_CONFIG__?: RuntimeConfigStore;
};

function readConfigValue(
  name: AdminRuntimeConfigKey,
  fallbackValue: string | undefined,
): string | undefined {
  const runtimeValue = runtimeConfigGlobal.__REMNASTORE_RUNTIME_CONFIG__?.[name];
  const candidate = typeof runtimeValue === "string" ? runtimeValue : fallbackValue;
  const normalized = candidate?.trim();
  return normalized ? normalized : undefined;
}

export const apiBaseUrl =
  (readConfigValue("VITE_API_BASE_URL", import.meta.env.VITE_API_BASE_URL) ??
    "http://localhost:8000").replace(/\/+$/, "");
