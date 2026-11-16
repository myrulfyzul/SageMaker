/// Client-side checks that mirror Req 20.1 and 20.7. Each returns an error
/// message, or null when the value is valid.
library;

String? validateProductName(String? v) {
  final s = (v ?? '').trim();
  if (s.isEmpty) return 'Enter a name';
  if (s.length > 200) return 'Name must be 200 characters or fewer';
  return null;
}

String? validateProductDescription(String? v) =>
    (v ?? '').trim().length > 2000
        ? 'Description must be 2000 characters or fewer'
        : null;

/// Parses a price typed in ringgit ("12", "12.5", "12.34") to sen, or null.
int? parsePriceSen(String? v) {
  final s = (v ?? '').trim();
  final m = RegExp(r'^(\d+)(?:\.(\d{1,2}))?$').firstMatch(s);
  if (m == null) return null;
  final whole = int.tryParse(m.group(1)!);
  if (whole == null) return null;
  final cents = int.parse((m.group(2) ?? '').padRight(2, '0'));
  return whole * 100 + cents;
}

String? validatePriceRm(String? v) {
  final sen = parsePriceSen(v);
  if (sen == null) return 'Enter a price such as 12.50';
  if (sen < 1 || sen > 99999999) return 'Price must be RM 0.01 to RM 999,999.99';
  return null;
}

String? validateWholeNumber(String? v,
    {required int max, required String label}) {
  final s = (v ?? '').trim();
  if (!RegExp(r'^\d+$').hasMatch(s)) return '$label must be a whole number';
  final n = int.tryParse(s);
  if (n == null || n > max) return '$label must be 0 to $max';
  return null;
}

String? validateStock(String? v) =>
    validateWholeNumber(v, max: 999999, label: 'Stock');

String? validateThreshold(String? v) =>
    validateWholeNumber(v, max: 999999, label: 'Threshold');

/// Allowed upload types and size (Req 20.5).
const maxImageBytes = 5 * 1024 * 1024;

String? validateImage(String name, int length) {
  final lower = name.toLowerCase();
  final ok = lower.endsWith('.png') ||
      lower.endsWith('.jpg') ||
      lower.endsWith('.jpeg') ||
      lower.endsWith('.webp');
  if (!ok) return 'Use a PNG, JPEG or WebP image';
  if (length > maxImageBytes) return 'Image must be 5 MB or smaller';
  return null;
}
