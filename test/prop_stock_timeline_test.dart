import 'package:glados/glados.dart';
import 'package:sagemaker_flutter/features/catalogue/data/catalogue_models.dart';
import 'package:sagemaker_flutter/features/orders/data/order_models.dart';

StockLevel levelFor(int stock, int threshold) {
  if (stock <= 0) return StockLevel.outOfStock;
  if (stock <= threshold) return StockLevel.lowStock;
  return StockLevel.inStock;
}

void main() {
  // Feature: sagemaker-asia-mobile-platform, Property 47: Stock status text and timeline rendering
  // **Validates: Requirements 9.11, 15.6, 15.7**
  Glados2(any.intInRange(0, 1000), any.intInRange(0, 1000))
      .test('stock label by stock and threshold', (stock, threshold) {
    final text = stockStatusText(levelFor(stock, threshold), stock);
    if (stock == 0) {
      expect(text, 'Out of stock');
    } else if (stock <= threshold) {
      expect(text, 'Low stock: $stock left');
    } else {
      expect(text, 'In stock');
    }
  });

  // mask selects which of the five steps appear in history; terminal: 0 none,
  // 1 cancelled, 2 payment_failed.
  Glados2(any.intInRange(0, 32), any.intInRange(0, 3))
      .test('timeline marks exactly the steps in history', (mask, terminal) {
    final present = <String>[
      for (var i = 0; i < timelineStatuses.length; i++)
        if (mask & (1 << i) != 0) timelineStatuses[i],
    ];
    final terminalStatus = [null, 'cancelled', 'payment_failed'][terminal];
    final history = [
      for (final s in present)
        OrderHistoryEntry(status: s, at: DateTime.utc(2025, 1, 1)),
      if (terminalStatus != null)
        OrderHistoryEntry(status: terminalStatus, at: DateTime.utc(2025, 1, 2)),
    ];
    final status = terminalStatus ?? (present.isEmpty ? 'placed' : present.last);

    final steps = buildTimeline(status, history);

    if (terminalStatus == null) {
      expect(steps.map((s) => s.status).toList(), timelineStatuses);
      for (final s in steps) {
        expect(s.reached, present.contains(s.status));
        expect(s.terminal, isFalse);
      }
    } else {
      expect(steps.map((s) => s.status).toList(),
          [...present, terminalStatus]);
      expect(steps.where((s) => s.terminal).length, 1);
      expect(steps.last.terminal, isTrue);
      expect(steps.last.status, terminalStatus);
      expect(steps.every((s) => s.reached), isTrue);
    }
  });
}
