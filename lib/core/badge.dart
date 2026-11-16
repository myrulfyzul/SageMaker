/// Badge label for a count: `null` (hidden) for 0 or less, the decimal count
/// for 1 to 99 and `99+` above 99 (Req 17.9, 18.4, 18.5, 18.6).
String? badgeLabel(int count) {
  if (count <= 0) return null;
  if (count > 99) return '99+';
  return count.toString();
}
