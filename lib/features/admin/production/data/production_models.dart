/// Production_Status sequence (Req 24.4).
const productionStatuses = [
  'order_confirmed',
  'production_assigned',
  'in_production',
  'quality_checking',
  'completed',
  'ready_for_fulfilment',
];

const productionPriorities = ['low', 'normal', 'high', 'urgent'];

/// Allowed next statuses (Req 24.4), including quality_checking back to
/// in_production. `order_confirmed` moves only through the assign form.
const _next = {
  'order_confirmed': ['production_assigned'],
  'production_assigned': ['in_production'],
  'in_production': ['quality_checking'],
  'quality_checking': ['completed', 'in_production'],
  'completed': ['ready_for_fulfilment'],
  'ready_for_fulfilment': <String>[],
};

List<String> nextStatuses(String status) =>
    List.of(_next[status] ?? const <String>[]);

String statusLabel(String s) {
  final t = s.replaceAll('_', ' ');
  return t.isEmpty ? t : t[0].toUpperCase() + t.substring(1);
}

class ProgressEntry {
  const ProgressEntry({required this.percent, required this.note, this.at});

  factory ProgressEntry.fromJson(Map<String, dynamic> j) => ProgressEntry(
        percent: (j['percent'] as num?)?.toInt() ?? 0,
        note: (j['note'] ?? '').toString(),
        at: j['createdAt']?.toString(),
      );

  final int percent;
  final String note;
  final String? at;
}

class ProductionJob {
  const ProductionJob({
    required this.id,
    required this.status,
    required this.priority,
    required this.productName,
    required this.quantity,
    this.orderId,
    this.artisanId,
    this.artisanName,
    this.deadline,
    this.progressPercent = 0,
    this.notes = '',
    this.overdue = false,
    this.history = const [],
  });

  factory ProductionJob.fromJson(Map<String, dynamic> j) => ProductionJob(
        id: (j['id'] as num).toInt(),
        status: (j['status'] ?? 'order_confirmed').toString(),
        priority: (j['priority'] ?? 'normal').toString(),
        productName: (j['productName'] ?? 'Job ${j['id']}').toString(),
        quantity: (j['quantity'] as num?)?.toInt() ?? 0,
        orderId: j['orderId']?.toString(),
        artisanId: (j['artisanId'] as num?)?.toInt(),
        artisanName: j['artisanName']?.toString(),
        deadline: j['deadline']?.toString(),
        progressPercent: (j['progressPercent'] as num?)?.toInt() ?? 0,
        notes: (j['notes'] ?? '').toString(),
        overdue: j['overdue'] == true,
        history: [
          for (final p in (j['progressHistory'] as List? ?? const []))
            if (p is Map) ProgressEntry.fromJson(Map<String, dynamic>.from(p)),
        ],
      );

  final int id;
  final String status;
  final String priority;
  final String productName;
  final int quantity;
  final String? orderId;
  final int? artisanId;
  final String? artisanName;
  final String? deadline;
  final int progressPercent;
  final String notes;

  /// Server-computed overdue flag (Req 24.9).
  final bool overdue;
  final List<ProgressEntry> history;
}

/// Combined AND filters (Req 24.12).
class ProductionFilters {
  const ProductionFilters({this.status, this.artisanId, this.priority});

  final String? status;
  final int? artisanId;
  final String? priority;

  bool get isEmpty => status == null && artisanId == null && priority == null;

  ProductionFilters copyWith({
    String? Function()? status,
    int? Function()? artisanId,
    String? Function()? priority,
  }) =>
      ProductionFilters(
        status: status != null ? status() : this.status,
        artisanId: artisanId != null ? artisanId() : this.artisanId,
        priority: priority != null ? priority() : this.priority,
      );

  @override
  bool operator ==(Object other) =>
      other is ProductionFilters &&
      other.status == status &&
      other.artisanId == artisanId &&
      other.priority == priority;

  @override
  int get hashCode => Object.hash(status, artisanId, priority);
}
