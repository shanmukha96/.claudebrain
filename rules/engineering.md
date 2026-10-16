---
paths: "**/*.{ts,tsx,js,jsx,mjs,cjs,py,go,rs,java,kt,kts,swift,m,mm,rb,php,cs,c,cpp,h,hpp,vue,svelte,dart,scala,lua,r,sh,ps1,sql,html,css,scss}"
---
# Engineering rules (load only when touching source code)

## Modularity — reusable without being speculative
1. One function, one job. If its description needs "and", split it.
2. Separate pure logic from I/O. Logic takes inputs and returns outputs; a thin outer layer does network, disk and DB.
3. Inject dependencies (clients, clocks, config) as parameters instead of importing globals, so pieces can be reused and tested alone.
4. Extract to a shared module on the second real use, not the first. No abstractions for imagined future callers.
5. Keep public interfaces small and stable; change internals freely behind them.
6. Prefer composition of small functions over flags that switch a function between modes.

## Example of rules 2 and 3

```ts
// ❌ logic, I/O and a hidden global tangled together
export async function chargeUser(id: string) {
  const user = await db.users.find(id);
  const total = user.cart.reduce((s, i) => s + i.price * i.qty, 0) * 1.08;
  await stripe.charge(user.card, total);
}

// ✅ pure, reusable core + thin I/O shell with injected dependencies
export const cartTotal = (items: Item[], taxRate: number) =>
  items.reduce((s, i) => s + i.price * i.qty, 0) * (1 + taxRate);

export async function chargeUser(id: string, deps: { db: Db; pay: Payments; taxRate: number }) {
  const user = await deps.db.users.find(id);
  await deps.pay.charge(user.card, cartTotal(user.cart, deps.taxRate));
}
```

## Quality
7. Handle errors at the boundary where you can act on them; never swallow them silently.
8. Names say what a thing is or does; no `data`, `tmp`, `handle2`.
9. New logic gets a test. A bug fix gets a test that failed before the fix.
10. Match the project's existing conventions over these rules when they conflict, and note the conflict in PLAN.md history.
