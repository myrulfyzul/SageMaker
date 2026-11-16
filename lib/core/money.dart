/// Formats an amount in sen as `RM 12.34`. Identical to the old `money()` in main.dart.
String formatRm(int sen) => 'RM ${(sen / 100).toStringAsFixed(2)}';
