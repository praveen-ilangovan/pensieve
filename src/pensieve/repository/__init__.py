"""
repository — the storage port + its adapters.

`base` defines the storage-agnostic contract (`Repository` + `UnitOfWork`); `sqlite`
and `memory` are interchangeable implementations. Services depend only on `base`.
"""
