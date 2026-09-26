import { useCallback, useState } from "react";
import {
  AlertTriangle,
  Cpu,
  Database,
  Info,
  Moon,
  Palette,
  RefreshCw,
  Server,
  ShieldCheck,
  Sun,
  Trash2,
  User,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { ConfirmationDialog } from "@/components/shared/confirmation-dialog";
import { ErrorState, LoadingState } from "@/components/shared/async-state";
import { LogoMark } from "@/components/brand/logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Separator, Switch } from "@/components/ui/controls";
import { Reveal } from "@/components/motion/motion";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api/endpoints";
import { notifyError, notifySuccess } from "@/lib/notify";
import { useAppStore } from "@/store/app-store";
import { cn, formatBytes } from "@/lib/utils";

function SettingRow({
  title,
  description,
  control,
}: {
  title: string;
  description: string;
  control: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-6 py-4">
      <div className="min-w-0">
        <p className="text-[13.5px] font-medium text-ink">{title}</p>
        <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-muted">{description}</p>
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  );
}

function InfoRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-[12.5px]">
      <span className="text-ink-faint">{label}</span>
      <span className={cn("truncate text-right text-ink", mono && "mono")}>{value}</span>
    </div>
  );
}

export function SettingsPage() {
  const theme = useAppStore((state) => state.theme);
  const setTheme = useAppStore((state) => state.setTheme);
  const sidebarCollapsed = useAppStore((state) => state.sidebarCollapsed);
  const setSidebarCollapsed = useAppStore((state) => state.setSidebarCollapsed);
  const denseLists = useAppStore((state) => state.denseLists);
  const setDenseLists = useAppStore((state) => state.setDenseLists);
  const profileName = useAppStore((state) => state.profileName);
  const setProfileName = useAppStore((state) => state.setProfileName);
  const bump = useAppStore((state) => state.bumpDatasetsVersion);
  const clearCache = useAppStore((state) => state.clearCache);
  const setSelectedDatasetId = useAppStore((state) => state.setSelectedDatasetId);

  const health = useAsync(() => api.health(), []);
  const [nameDraft, setNameDraft] = useState(profileName);

  const saveProfile = useCallback(() => {
    setProfileName(nameDraft.trim());
    notifySuccess("Profile saved", "Your display name is stored locally in this browser.");
  }, [nameDraft, setProfileName]);

  const clearHistory = useCallback(async () => {
    try {
      const result = await api.clearHistory();
      clearCache();
      bump();
      setSelectedDatasetId(null);
      notifySuccess(
        "History cleared",
        `${result.deleted_datasets} dataset(s) and ${result.deleted_reports} report(s) removed.`,
      );
    } catch (caught) {
      notifyError(caught);
    }
  }, [bump, clearCache, setSelectedDatasetId]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Appearance, workspace and system status for this machine. Preferences are stored locally."
        actions={
          <Button variant="secondary" size="md" onClick={health.reload} loading={health.loading}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh status
          </Button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Reveal>
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/30 bg-accent-soft text-accent">
                    <Palette className="h-4 w-4" />
                  </span>
                  <div>
                    <CardTitle>Appearance</CardTitle>
                    <CardDescription>How VISORA looks on this device</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-2">
                <div className="grid gap-3 sm:grid-cols-2">
                  {([
                    { id: "dark", label: "Dark", description: "Deep indigo canvas", icon: Moon },
                    { id: "light", label: "Light", description: "Bright workspace", icon: Sun },
                  ] as const).map((option) => {
                    const Icon = option.icon;
                    const active = theme === option.id;
                    return (
                      <button
                        key={option.id}
                        type="button"
                        onClick={() => setTheme(option.id)}
                        className={cn(
                          "flex items-center gap-3 rounded-xl border px-4 py-3.5 text-left transition-all",
                          active
                            ? "border-accent/50 bg-accent-soft"
                            : "border-line bg-surface-sunken hover:border-line-strong",
                        )}
                      >
                        <span
                          className={cn(
                            "flex h-9 w-9 items-center justify-center rounded-lg border",
                            active
                              ? "border-accent/40 bg-surface-raised text-accent"
                              : "border-line bg-surface-raised text-ink-muted",
                          )}
                        >
                          <Icon className="h-4 w-4" />
                        </span>
                        <span>
                          <span className="block text-[13.5px] font-medium text-ink">
                            {option.label}
                          </span>
                          <span className="block text-[12px] text-ink-muted">
                            {option.description}
                          </span>
                        </span>
                        {active && (
                          <Badge variant="accent" className="ml-auto">
                            Active
                          </Badge>
                        )}
                      </button>
                    );
                  })}
                </div>

                <Separator className="my-3" />

                <SettingRow
                  title="Collapsed sidebar"
                  description="Keep navigation compact and give charts more room."
                  control={
                    <Switch
                      checked={sidebarCollapsed}
                      onCheckedChange={setSidebarCollapsed}
                      aria-label="Toggle collapsed sidebar"
                    />
                  }
                />
                <Separator />
                <SettingRow
                  title="Dense dataset lists"
                  description="Show more rows per screen in dataset lists."
                  control={
                    <Switch
                      checked={denseLists}
                      onCheckedChange={setDenseLists}
                      aria-label="Toggle dense lists"
                    />
                  }
                />
              </CardContent>
            </Card>
          </Reveal>

          <Reveal delay={0.06}>
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-line-strong bg-surface-sunken text-ink-muted">
                    <User className="h-4 w-4" />
                  </span>
                  <div>
                    <CardTitle>Account</CardTitle>
                    <CardDescription>Local profile for this workspace</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <div className="flex flex-wrap items-end gap-3">
                  <div className="min-w-[240px] flex-1">
                    <label
                      htmlFor="display-name"
                      className="mb-1.5 block text-[12px] font-medium text-ink-muted"
                    >
                      Display name
                    </label>
                    <Input
                      id="display-name"
                      value={nameDraft}
                      onChange={(event) => setNameDraft(event.target.value)}
                      placeholder="Your name"
                      maxLength={48}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") saveProfile();
                      }}
                    />
                  </div>
                  <Button variant="secondary" size="md" onClick={saveProfile}>
                    Save
                  </Button>
                </div>
                <p className="mt-3 flex items-start gap-2 text-[12px] leading-relaxed text-ink-faint">
                  <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  VISORA runs locally with no authentication backend — this name only personalizes
                  the interface and never leaves your machine.
                </p>
              </CardContent>
            </Card>
          </Reveal>

          <Reveal delay={0.1}>
            <Card className="border-rose/30">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-rose/30 bg-rose/10 text-rose">
                    <AlertTriangle className="h-4 w-4" />
                  </span>
                  <div>
                    <CardTitle>Danger zone</CardTitle>
                    <CardDescription>Irreversible workspace operations</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-rose/25 bg-rose/6 px-4 py-3.5">
                  <div className="min-w-0">
                    <p className="text-[13.5px] font-medium text-ink">Clear all history</p>
                    <p className="mt-0.5 text-[12.5px] text-ink-muted">
                      Deletes every stored dataset, analytical table and generated report.
                    </p>
                  </div>
                  <ConfirmationDialog
                    title="Clear all history?"
                    description="Every stored dataset, analytical table and generated report will be permanently removed. This can't be undone."
                    confirmLabel="Clear everything"
                    onConfirm={clearHistory}
                    trigger={
                      <Button variant="danger" size="md">
                        <Trash2 className="h-3.5 w-3.5" />
                        Clear history
                      </Button>
                    }
                  />
                </div>
              </CardContent>
            </Card>
          </Reveal>
        </div>

        <div className="space-y-4">
          <Reveal delay={0.08}>
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-emerald/30 bg-emerald/10 text-emerald">
                    <Server className="h-4 w-4" />
                  </span>
                  <div>
                    <CardTitle>System status</CardTitle>
                    <CardDescription>FastAPI bridge + Python backend</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                {health.loading && !health.data ? (
                  <LoadingState variant="table" rows={3} />
                ) : health.error ? (
                  <ErrorState
                    compact
                    error={health.error}
                    title="API unreachable"
                    onRetry={health.reload}
                  />
                ) : health.data ? (
                  <>
                    <div className="mb-3 flex items-center gap-2 rounded-lg border border-emerald/30 bg-emerald/8 px-3.5 py-2.5 text-[12.5px] text-emerald">
                      <ShieldCheck className="h-4 w-4" />
                      Operational · v{health.data.version}
                    </div>
                    <div className="divide-y divide-[var(--line)]">
                      <InfoRow label="Datasets" value={String(health.data.datasets)} />
                      <InfoRow label="Reports" value={String(health.data.reports)} />
                      <InfoRow
                        label="Unified snapshot"
                        value={health.data.currentReport ? "present" : "none"}
                      />
                      <InfoRow
                        label="Upload limit"
                        value={formatBytes(health.data.uploadLimitBytes)}
                        mono
                      />
                    </div>
                  </>
                ) : null}
              </CardContent>
            </Card>
          </Reveal>

          <Reveal delay={0.12}>
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-accent/30 bg-accent-soft text-accent">
                    <Cpu className="h-4 w-4" />
                  </span>
                  <div>
                    <CardTitle>AI engine</CardTitle>
                    <CardDescription>Provider chain status</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                <Badge
                  variant={health.data?.ai.mode === "provider_chain" ? "accent" : "neutral"}
                  className="mb-3 capitalize"
                >
                  {(health.data?.ai.mode ?? "unknown").replace("_", " ")}
                </Badge>
                <p className="text-[12.5px] leading-relaxed text-ink-muted">
                  {health.data?.ai.mode === "provider_chain"
                    ? `${health.data?.ai.configuredProviders} of ${health.data?.ai.totalSlots} provider slots configured.`
                    : "No provider is configured, so VISORA uses its local analytical fallback: deterministic findings and evidence without external calls."}
                </p>
                <Separator className="my-3" />
                <p className="text-[12px] leading-relaxed text-ink-faint">
                  Configure providers with <span className="mono text-ink-muted">VISORA_*</span>{" "}
                  environment variables or Streamlit secrets. Keys are never sent to this frontend.
                </p>
              </CardContent>
            </Card>
          </Reveal>

          <Reveal delay={0.16}>
            <Card>
              <CardContent className="flex items-start gap-3.5 pt-5">
                <LogoMark size={40} animate={false} />
                <div className="min-w-0">
                  <p className="text-[13.5px] font-semibold tracking-tight text-ink">VISORA BI</p>
                  <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-muted">
                    Make the hidden obvious. Numbers first, interpretation second — with the
                    evidence to back it up.
                  </p>
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    <Badge variant="neutral">
                      <Database className="h-3 w-3" />
                      local-first
                    </Badge>
                    <Badge variant="neutral">evidence-backed</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          </Reveal>
        </div>
      </div>
    </div>
  );
}
