/// The 16 Malaysian states and federal territories (same list and spelling as the backend).
const List<String> malaysianStates = [
  'Johor',
  'Kedah',
  'Kelantan',
  'Melaka',
  'Negeri Sembilan',
  'Pahang',
  'Perak',
  'Perlis',
  'Pulau Pinang',
  'Sabah',
  'Sarawak',
  'Selangor',
  'Terengganu',
  'Kuala Lumpur',
  'Labuan',
  'Putrajaya',
];

/// Seeded product categories (Req 9.13).
const List<String> productCategories = [
  'Tote bags',
  'Fabric books',
  'Toys',
  'Gifts',
  'Accessories',
];

/// Fulfilment statuses of an order.
const List<String> fulfilmentStatuses = [
  'placed',
  'confirmed',
  'preparing',
  'shipped',
  'delivered',
  'cancelled',
  'payment_failed',
];

/// Production job statuses, independent of fulfilment status.
const List<String> productionStatuses = [
  'order_confirmed',
  'production_assigned',
  'in_production',
  'quality_checking',
  'completed',
  'ready_for_fulfilment',
];
