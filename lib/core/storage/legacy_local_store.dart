import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'preferences_provider.dart';

/// `shared_preferences` keys written by the earlier prototype (`main.dart`).
/// They are kept unchanged so existing guest data is read as-is (Req 1.1, 1.7).
const legacyFavouritesKey = 'sagemaker_saved_product_ids';
const legacyCartKey = 'sagemaker_demo_cart_v1';
const legacyOrdersKey = 'sagemaker_demo_orders_v1';

/// An order placed by the earlier prototype, tracked with its guest token.
class SavedOrder {
  const SavedOrder(this.id, this.token);
  final String id;
  final String token;

  @override
  bool operator ==(Object other) =>
      other is SavedOrder && other.id == id && other.token == token;

  @override
  int get hashCode => Object.hash(id, token);
}

/// Raw access to the three prototype keys. Reads never throw (corrupt or
/// blocked storage yields empty data) and writes swallow storage errors so the
/// app keeps working in memory, as the old stores did.
class LegacyLocalStore {
  LegacyLocalStore(this._preferences);

  /// A store without backing storage (storage blocked, or tests).
  LegacyLocalStore.memory() : _preferences = null;

  final SharedPreferences? _preferences;

  List<String> readFavouriteIds() {
    try {
      return _preferences?.getStringList(legacyFavouritesKey) ?? <String>[];
    } catch (_) {
      return <String>[];
    }
  }

  Future<void> writeFavouriteIds(Iterable<String> ids) async {
    try {
      await _preferences?.setStringList(legacyFavouritesKey, ids.toList());
    } catch (_) {}
  }

  /// Raw product id to quantity map (no clamping; callers clamp).
  Map<String, int> readCart() {
    try {
      final raw = jsonDecode(_preferences?.getString(legacyCartKey) ?? '{}');
      if (raw is! Map) return <String, int>{};
      return {
        for (final e in raw.entries)
          if (e.value is num) e.key.toString(): (e.value as num).toInt(),
      };
    } catch (_) {
      return <String, int>{};
    }
  }

  Future<void> writeCart(Map<String, int> quantities) async {
    try {
      await _preferences?.setString(legacyCartKey, jsonEncode(quantities));
    } catch (_) {}
  }

  Future<void> clearCart() async {
    try {
      await _preferences?.remove(legacyCartKey);
    } catch (_) {}
  }

  Future<void> clearFavourites() async {
    try {
      await _preferences?.remove(legacyFavouritesKey);
    } catch (_) {}
  }

  List<SavedOrder> readOrders() {
    try {
      final list = jsonDecode(_preferences?.getString(legacyOrdersKey) ?? '[]');
      if (list is! List) return <SavedOrder>[];
      return [
        for (final e in list)
          if (e is Map && e['id'] is String && e['token'] is String)
            SavedOrder(e['id'] as String, e['token'] as String),
      ];
    } catch (_) {
      return <SavedOrder>[];
    }
  }

  Future<void> writeOrders(List<SavedOrder> orders) async {
    try {
      await _preferences?.setString(
        legacyOrdersKey,
        jsonEncode([
          for (final o in orders) {'id': o.id, 'token': o.token}
        ]),
      );
    } catch (_) {}
  }
}

/// Resolves once `shared_preferences` has been opened (null storage tolerated).
final legacyLocalStoreProvider = FutureProvider<LegacyLocalStore>((ref) async {
  final prefs = await ref.watch(sharedPreferencesProvider.future);
  return LegacyLocalStore(prefs);
});
