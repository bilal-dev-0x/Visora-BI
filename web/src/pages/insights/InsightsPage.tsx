import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Brain,
  CheckCircle2,
  Lightbulb,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/shared/async-state";
import { PriorityBadge } from "@/components/shared/kpi-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Reveal, Stagger, StaggerItem } from "@/components/motion/motion";
import { useAsync } from "@/hooks/use-async";
import { api } from "@/lib/api/endpoints";
import type { AiInsight, Finding } from "@/lib/api/types";
import { useAppStore } from "@/store/app-store";
import { cn, formatCompact, formatRelative, truncate } from "@/lib/utils";

const INSIGHT_ICONS = [TrendingUp, Target, Lightbulb, ShieldAlert, Sparkles];

function insightIcon(index: number) {
  const Icon = INSIGHT_ICONS[index % INSIGHT_ICONS.length];
  return <Icon className="h-4 w-4" />;
}

function InsightCard({ insight, index }: { insight: AiInsight; index: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <StaggerItem>
      <Card className="group h-full transition-all duration-300 hover:-translate-y-0.5 hover:border-line-strong">
        <CardContent className="pt-5">
          <div className="flex items-start justify-between gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-accent/30 bg-accent-soft text-accent">
              {insightIcon(index)}
            </span>
            <PriorityBadge priority={insight.priority} />
          </div>
          <p className="mt-3.5 text-[14.5px] font-semibold leading-snug tracking-tight text-ink">
            {insight.title}
          </p>
          <Badge variant="neutral" className="mt-2 capitalize">
            {insight.type.replace(/_/g, " ")}
          </Badge>
          <p
            className={cn(
              "mt-2.5 text-[13px] leading-relaxed text-ink-muted",
              !expanded && "line-clamp-3",
            )}
          >
            {insight.explanation}
          </p>
          {insight.explanation.length > 150 && (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              className="mt-1.5 text-[12.5px] font-medium text-accent transition-colors hover:text-ink"
            >
              {expanded ? "Show less" : "Read more"}
            </button>
          )}

          {insight.evidence.length > 0 && (
            <div className="mt-3.5 space-y-1.5 border-t border-line pt-3">
              <p className="text-[10.5px] font-semibold uppercase tracking-wider text-ink-faint">
                Evidence
              </p>
              {insight.evidence.slice(0, 3).map((item) => (
                <div key={item.id} className="flex items-start gap-2 text-[12px]">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-cyan" />
                  <span className="text-ink-muted">
                    {item.title}
                    {item.value !== null && (
                      <span className="mono text-ink-faint"> · {formatCompact(item.value)}</span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </StaggerItem>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-line bg-surface-sunken px-3.5 py-3 transition-colors hover:border-line-strong">
      <PriorityBadge priority={finding.priority} />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium leading-snug text-ink">{finding.title}</p>
        <p className="mono mt-1 text-[11.5px] text-ink-faint">
          {finding.type} · {finding.source}
          {finding.period ? ` · ${finding.period}` : ""}
          {finding.column ? ` · ${finding.column}` : ""}
        </p>
      </div>
      {finding.value !== null && (
        <span className="mono shrink-0 text-[12.5px] tabular text-ink-muted">
          {formatCompact(finding.value)}
        </span>
      )}
    </div>
  );
}

export function InsightsPage() {
  const navigate = useNavigate();
  const datasetsVersion = useAppStore((state) => state.datasetsVersion);

  const { data, loading, error, reload } = useAsync(
    () => api.insights(),
    [datasetsVersion],
  );

  if (loading && !data) return <LoadingState variant="cards" />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;

  if (!data || !data.available) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="AI Insights"
          description="Evidence-backed interpretation of your data — risks, opportunities and what to do next."
        />
        <EmptyState
          icon={
            <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-line-strong bg-surface-raised text-ink-muted">
              <Sparkles className="h-5 w-5" />
            </div>
          }
          title="No analysis yet"
          description="Run an analysis on any dataset and VISORA will produce prioritized findings, evidence chains and an AI interpretation you can act on."
          action={
            <Button variant="primary" onClick={() => navigate("/analytics")}>
              Go to Analytics
              <ArrowRight className="h-4 w-4" />
            </Button>
          }
        />
      </div>
    );
  }

  const criticalCount = data.findings.filter((finding) => finding.priority === "critical").length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Insights"
        description="What the analysis means — every claim traces back to evidence in your data."
        meta={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={data.source === "ai" ? "accent" : "neutral"}>
              <Brain className="h-3 w-3" />
              {data.source === "ai"
                ? `AI · ${data.providerUsed ?? "provider"}`
                : "Local evidence fallback"}
            </Badge>
            <Badge variant={criticalCount > 0 ? "danger" : "success"}>
              {criticalCount} critical
            </Badge>
            <Badge variant="neutral">generated {formatRelative(data.generatedAt)}</Badge>
          </div>
        }
        actions={
          <Button variant="secondary" size="md" onClick={reload} loading={loading}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        }
      />

      <Reveal>
        <Card className="relative overflow-hidden">
          <div
            aria-hidden
            className="pointer-events-none absolute -left-20 -top-24 h-56 w-56 rounded-full opacity-30 blur-3xl"
            style={{ backgroundImage: "var(--gradient-accent)" }}
          />
          <CardContent className="relative pt-6">
            <div className="flex items-center gap-2 text-[11.5px] font-semibold uppercase tracking-wider text-ink-faint">
              <Sparkles className="h-3.5 w-3.5 text-accent" />
              Summary
            </div>
            <p className="mt-2.5 max-w-3xl text-[16px] leading-relaxed text-ink">
              {data.summary || "No summary was produced for this analysis."}
            </p>
            <div className="mt-4 flex flex-wrap gap-4 text-[12.5px] text-ink-muted">
              <span className="mono">{data.dataset?.original_filename ?? "dataset"}</span>
              <span>·</span>
              <span>{data.insights.length} insights</span>
              <span>·</span>
              <span>{data.evidence.length} evidence items</span>
              <span>·</span>
              <span>{data.findings.length} findings</span>
            </div>
            {data.skippedReason && (
              <p className="mt-3 rounded-lg border border-amber/30 bg-amber/8 px-3.5 py-2.5 text-[12.5px] text-amber">
                {data.skippedReason}
              </p>
            )}
          </CardContent>
        </Card>
      </Reveal>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Tabs defaultValue="insights">
            <TabsList>
              <TabsTrigger value="insights">Insights ({data.insights.length})</TabsTrigger>
              <TabsTrigger value="findings">Findings ({data.findings.length})</TabsTrigger>
              <TabsTrigger value="evidence">Evidence ({data.evidence.length})</TabsTrigger>
            </TabsList>

            <TabsContent value="insights">
              {data.insights.length > 0 ? (
                <Stagger className="grid gap-4 md:grid-cols-2" stagger={0.07}>
                  {data.insights.map((insight, index) => (
                    <InsightCard key={insight.id} insight={insight} index={index} />
                  ))}
                </Stagger>
              ) : (
                <EmptyState
                  compact
                  title="No insights generated"
                  description="The analytical layer found nothing worth escalating for this dataset."
                />
              )}
            </TabsContent>

            <TabsContent value="findings">
              <div className="space-y-2.5">
                {data.findings.length > 0 ? (
                  data.findings.map((finding) => (
                    <FindingRow key={finding.id} finding={finding} />
                  ))
                ) : (
                  <EmptyState
                    compact
                    icon={<CheckCircle2 className="h-5 w-5 text-emerald" />}
                    title="Nothing to flag"
                    description="No prioritized findings were produced for this analysis."
                  />
                )}
              </div>
            </TabsContent>

            <TabsContent value="evidence">
              <div className="space-y-2.5">
                {data.evidence.length > 0 ? (
                  data.evidence.map((item) => (
                    <div
                      key={item.id}
                      className="flex items-start gap-3 rounded-lg border border-line bg-surface-sunken px-3.5 py-3"
                    >
                      <Badge variant="neutral" className="capitalize">
                        {item.type}
                      </Badge>
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] leading-snug text-ink">{item.title}</p>
                        <p className="mono mt-1 text-[11.5px] text-ink-faint">
                          {item.source}
                          {item.period ? ` · ${item.period}` : ""}
                          {item.column ? ` · ${item.column}` : ""}
                          {item.date_column ? ` · ${item.date_column}` : ""}
                        </p>
                      </div>
                      {item.value !== null && (
                        <span className="mono shrink-0 text-[12.5px] tabular text-ink-muted">
                          {formatCompact(item.value)}
                        </span>
                      )}
                    </div>
                  ))
                ) : (
                  <EmptyState
                    compact
                    title="No evidence recorded"
                    description="Evidence appears after the analysis pipeline runs."
                  />
                )}
              </div>
            </TabsContent>
          </Tabs>
        </div>

        <div className="space-y-4">
          <Reveal delay={0.08}>
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-rose/30 bg-rose/10 text-rose">
                    <ShieldAlert className="h-4 w-4" />
                  </span>
                  <div>
                    <CardTitle>Risks</CardTitle>
                    <CardDescription>What could go wrong</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                {data.risks.length > 0 ? (
                  <ul className="space-y-2.5">
                    {data.risks.map((risk, index) => (
                      <li key={index} className="flex items-start gap-2.5 text-[13px] leading-relaxed text-ink-muted">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-rose" />
                        {truncate(risk, 220)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[13px] text-ink-muted">No risks were identified.</p>
                )}
              </CardContent>
            </Card>
          </Reveal>

          <Reveal delay={0.12}>
            <Card>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-emerald/30 bg-emerald/10 text-emerald">
                    <Target className="h-4 w-4" />
                  </span>
                  <div>
                    <CardTitle>Opportunities</CardTitle>
                    <CardDescription>Where the upside is</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-4">
                {data.opportunities.length > 0 ? (
                  <ul className="space-y-2.5">
                    {data.opportunities.map((opportunity, index) => (
                      <li key={index} className="flex items-start gap-2.5 text-[13px] leading-relaxed text-ink-muted">
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald" />
                        {truncate(opportunity, 220)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-[13px] text-ink-muted">No opportunities were identified.</p>
                )}
              </CardContent>
            </Card>
          </Reveal>

          <Reveal delay={0.16}>
            <Card>
              <CardContent className="pt-5">
                <p className="text-[12.5px] leading-relaxed text-ink-faint">
                  VISORA shows its work: deterministic findings come from the analysis engines, and
                  the AI layer is only asked to interpret results that already exist.
                </p>
                <Button
                  variant="secondary"
                  size="sm"
                  className="mt-3 w-full"
                  onClick={() => navigate("/reports")}
                >
                  View full report
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </CardContent>
            </Card>
          </Reveal>
        </div>
      </div>
    </div>
  );
}
