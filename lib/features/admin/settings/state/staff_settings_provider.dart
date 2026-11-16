import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/api_client.dart';

/// `/api/staff/settings` (default low-stock threshold).
class StaffSettingsRepository {
  StaffSettingsRepository(this._client);
  final ApiClient _client;

  Future<int> getThreshold() async {
    final b = await _client.get('/api/staff/settings');
    return ((b as Map)['defaultLowStockThreshold'] as num).toInt();
  }

  Future<int> setThreshold(int v) async {
    final b = await _client
        .put('/api/staff/settings', body: {'defaultLowStockThreshold': v});
    return ((b as Map)['defaultLowStockThreshold'] as num).toInt();
  }
}

/// Whole number from 0 to 999,999,999.
String? validateDefaultThreshold(String? v) {
  final s = (v ?? '').trim();
  if (!RegExp(r'^\d+$').hasMatch(s)) return 'Enter a whole number';
  final n = int.tryParse(s);
  if (n == null || n > 999999999) return 'Must be 0 to 999,999,999';
  return null;
}

final staffSettingsRepositoryProvider = Provider<StaffSettingsRepository>(
    (ref) => StaffSettingsRepository(ref.watch(apiClientProvider)));

final defaultThresholdProvider = FutureProvider.autoDispose<int>(
    (ref) => ref.watch(staffSettingsRepositoryProvider).getThreshold());
