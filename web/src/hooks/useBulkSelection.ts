/**
 * Pure-state bulk-selection hook.
 *
 * Generic over the ID type (typically string). Provides the four
 * primitives every list view needs:
 *
 *   has(id)       boolean — is this id selected?
 *   toggle(id)    flip selection for one id
 *   setMany(ids)  set the selection to exactly these ids (use for
 *                  Select-all / Select-page)
 *   clear()       deselect everything
 *
 * Plus:
 *   ids           Array<T> of currently-selected ids (stable order
 *                  by insertion)
 *   count         len(ids)
 */
import { useCallback, useMemo, useState } from 'react';

export interface BulkSelection<T> {
  ids:     T[];
  count:   number;
  has:     (id: T) => boolean;
  toggle:  (id: T) => void;
  setMany: (ids: T[]) => void;
  clear:   () => void;
}

export function useBulkSelection<T extends string | number = string>(): BulkSelection<T> {
  // We use a Set under the hood for O(1) has() but expose an Array so
  // consumers get deterministic ordering when calling out to the API.
  const [setState, setSet] = useState<Set<T>>(() => new Set<T>());

  const has = useCallback((id: T) => setState.has(id), [setState]);

  const toggle = useCallback((id: T) => {
    setSet((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const setMany = useCallback((ids: T[]) => {
    setSet(new Set(ids));
  }, []);

  const clear = useCallback(() => setSet(new Set()), []);

  const ids = useMemo(() => Array.from(setState), [setState]);

  return { ids, count: ids.length, has, toggle, setMany, clear };
}
