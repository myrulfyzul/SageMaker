import 'package:glados/glados.dart';
import 'package:sagemaker_flutter/core/badge.dart';

void main() {
  // Feature: sagemaker-asia-mobile-platform, Property 31: Badge label
  // **Validates: Requirements 17.9, 17.10, 18.4, 18.5, 18.6**
  Glados(any.intInRange(0, 100000)).test('badge label by count range', (n) {
    final label = badgeLabel(n);
    if (n == 0) {
      expect(label, isNull);
    } else if (n <= 99) {
      expect(label, n.toString());
    } else {
      expect(label, '99+');
    }
  });

  Glados(any.int).test('non-positive counts are hidden', (n) {
    if (n <= 0) expect(badgeLabel(n), isNull);
  });
}
