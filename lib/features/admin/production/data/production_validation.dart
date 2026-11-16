/// Assign-form rules (Req 24.3, 24.8) and progress rules (Req 24.6, 24.7).
String? validateJobQuantity(String? v) {
  final n = int.tryParse((v ?? '').trim());
  if (n == null || n < 1 || n > 999999) {
    return 'Quantity must be a whole number from 1 to 999,999';
  }
  return null;
}

/// [today] is injectable for tests. Deadline is `YYYY-MM-DD` and must not be
/// earlier than today.
String? validateDeadline(String? v, {DateTime? today}) {
  final t = (v ?? '').trim();
  if (!RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(t)) {
    return 'Use the format YYYY-MM-DD';
  }
  final d = DateTime.tryParse(t);
  if (d == null || d.toIso8601String().substring(0, 10) != t) {
    return 'Enter a valid date';
  }
  final now = today ?? DateTime.now();
  if (d.isBefore(DateTime(now.year, now.month, now.day))) {
    return 'Deadline must not be earlier than today';
  }
  return null;
}

String? validateJobNotes(String? v) =>
    (v ?? '').length > 1000 ? 'Notes must be at most 1000 characters' : null;

String? validateProgressPercent(String? v) {
  final n = int.tryParse((v ?? '').trim());
  if (n == null || n < 0 || n > 100) {
    return 'Progress must be a whole number from 0 to 100';
  }
  return null;
}

String? validateProgressNote(String? v) =>
    (v ?? '').length > 500 ? 'Note must be at most 500 characters' : null;
