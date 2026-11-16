# Version 2 — In-app demo commerce

Reuses the previous green-and-cream Sagemaker Flutter project.

- Home, Shop, Saved, Orders, More navigation.
- In-app cart, quantity and totals; no external checkout links.
- Demo-only checkout options and order details screen; no live payment processing.
- Local Python FastAPI / SQLite order store and status tracking.
- Demo admin script to advance `placed → packing → shipped → delivered`.
- Sample/fictitious prices labelled DEMO throughout.
- This is an independent prototype and doesn't transmit orders or money to Sagemaker.
