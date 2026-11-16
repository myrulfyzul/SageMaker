/// Client-side checks that mirror Req 21.2 to 21.6.
library;

const maxDelta = 999999999;

String? validateDelta(String? v) {
  final s = (v ?? '').trim();
  if (!RegExp(r'^[+-]?\d+$').hasMatch(s)) return 'Enter a whole number';
  final n = int.tryParse(s.startsWith('+') ? s.substring(1) : s);
  if (n == null || n == 0) return 'Change must not be 0';
  if (n.abs() > maxDelta) return 'Change must be within $maxDelta';
  return null;
}

int parseDelta(String v) {
  final s = v.trim();
  return int.parse(s.startsWith('+') ? s.substring(1) : s);
}

String? validateReason(String? v) {
  final s = (v ?? '').trim();
  if (s.isEmpty) return 'Enter a reason';
  if (s.length > 255) return 'Reason must be 255 characters or fewer';
  return null;
}

String? validateInventoryThreshold(String? v) {
  final s = (v ?? '').trim();
  if (!RegExp(r'^\d+$').hasMatch(s)) return 'Enter a whole number';
  final n = int.tryParse(s);
  if (n == null || n > maxDelta) return 'Threshold must be 0 to $maxDelta';
  return null;
}
