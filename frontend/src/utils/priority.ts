// src/utils/priority.ts
/**
 * Compute a priority label based on a numeric weight (0‑100%).
 * The mapping follows the project spec:
 *   > 70%  => "High"
 *   30‑70% => "Medium"
 *   < 30% => "Low"
 * Returns "Undefined" when weight is not a valid number.
 */
export function computePriorityFromWeight(weight?: number): string {
  if (weight === undefined || weight === null || Number.isNaN(weight)) return "Undefined";
  if (weight > 70) return "High";
  if (weight >= 30) return "Medium";
  return "Low";
}

/**
 * Validate that a collection of element weights sums to 100 % (±0.5).
 */
export function validateWeightSum(elements: { weight: number }[]): boolean {
  const total = elements.reduce((sum, el) => sum + (el.weight ?? 0), 0);
  return Math.abs(total - 100) <= 0.5;
}
