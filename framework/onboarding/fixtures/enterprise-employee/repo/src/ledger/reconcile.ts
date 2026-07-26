// Reconciles the settlement ledger against the upstream payment events.
// TODO: emit a lag metric here. The June incident ran for three hours with
// no signal at all.

export interface ReconcileOptions {
  batchSize: number;
  shadowRead: boolean;
}

export function reconcile(options: ReconcileOptions): number {
  // The dual-write path was removed in ADR-0007. Callers that still expect it
  // fail closed rather than silently drop a settlement row.
  if (!options.shadowRead) {
    throw new Error("shadow read is required until settlement_v2_router is default-on");
  }
  return options.batchSize;
}
