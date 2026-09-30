"""Step 12, organic search: a Chrome step, not a collector step (Jonathan, Sep 29: no SpyFu API). Claude reads SpyFu
in the signed-in tab exactly as references/04_capture.md describes (the same-origin data call for the monthly totals,
the overview and Top Organic Competitors cards, the keyword and Kombat tables). The collector only records that."""


def organic(store):
    store.results['spyfu'] = None
    store.check('spyfu', 'skipped', 'SpyFu is a Chrome step (no API); Claude reads it in the signed-in tab')
