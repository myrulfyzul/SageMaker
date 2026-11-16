/// Client-side checks mirroring the backend rules (Req 16.1, 16.2, 16.3, 16.8).
const maxCustomOrderImages = 5;
const maxCustomOrderImageBytes = 5 * 1024 * 1024;
const allowedImageExtensions = ['png', 'jpg', 'jpeg', 'webp'];

String? validateProductType(String? value) {
  final n = value?.trim().length ?? 0;
  return n < 1 || n > 100 ? 'Product type must be 1 to 100 characters' : null;
}

String? validateDescription(String? value) {
  final n = value?.trim().length ?? 0;
  return n < 10 || n > 2000
      ? 'Description must be 10 to 2000 characters'
      : null;
}

/// Whole number from 1 to 500.
String? validateQuantity(String? value) {
  final v = value?.trim() ?? '';
  final n = RegExp(r'^[0-9]+$').hasMatch(v) ? int.tryParse(v) : null;
  return n == null || n < 1 || n > 500
      ? 'Quantity must be a whole number from 1 to 500'
      : null;
}

/// Today or later (date part only).
String? validatePreferredDate(DateTime? value, {DateTime? today}) {
  if (value == null) return 'Choose a preferred date';
  final now = today ?? DateTime.now();
  final start = DateTime(now.year, now.month, now.day);
  final d = DateTime(value.year, value.month, value.day);
  return d.isBefore(start) ? 'Preferred date must be today or later' : null;
}

/// Checks one image by file name and size; null when acceptable.
String? validateImage(String fileName, int sizeBytes) {
  final dot = fileName.lastIndexOf('.');
  final ext = dot < 0 ? '' : fileName.substring(dot + 1).toLowerCase();
  if (!allowedImageExtensions.contains(ext)) {
    return '$fileName: only PNG, JPEG or WebP images are allowed';
  }
  if (sizeBytes > maxCustomOrderImageBytes) {
    return '$fileName: image must be at most 5 MB';
  }
  return null;
}

/// `YYYY-MM-DD` as sent to the API.
String formatApiDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
