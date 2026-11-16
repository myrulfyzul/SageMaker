import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/app_failure.dart';
import '../../../core/storage/legacy_local_store.dart';
import '../../cart/data/guest_cart_repository.dart';
import '../../cart/state/cart_store.dart';
import '../../favourites/data/local_favourites_repository.dart';
import '../../favourites/state/favourites_store.dart';
import '../data/auth_user.dart';
import 'session_provider.dart';

/// What the first-sign-in sync did (Req 10.10, 10.11, 11.12, 11.13).
class SyncReport {
  const SyncReport({
    this.favouritesFailed = false,
    this.cartFailed = false,
    this.notMerged = const [],
  });

  /// Local favourites were kept for the next sign-in.
  final bool favouritesFailed;

  /// The cart merge failed; the whole local cart was kept.
  final bool cartFailed;

  /// Names (or ids) of cart lines that were capped or rejected.
  final List<String> notMerged;

  bool get isClean => !favouritesFailed && !cartFailed && notMerged.isEmpty;

  /// Message for the user, or null when everything synced.
  String? get message {
    final parts = <String>[];
    if (cartFailed) {
      parts.add('Your basket could not be merged and was kept on this device.');
    } else if (notMerged.isNotEmpty) {
      parts.add('Not merged into your basket: ${notMerged.join(', ')}.');
    }
    if (favouritesFailed) {
      parts.add('Saved favourites will upload at your next sign-in.');
    }
    return parts.isEmpty ? null : parts.join(' ');
  }
}

/// Uploads local favourites and merges the guest cart after sign-in. Neither
/// step can fail the sign-in itself.
class PostLoginSync {
  PostLoginSync(this._client, this._favourites, this._cart);

  final ApiClient _client;
  final LocalFavouritesRepository _favourites;
  final GuestCartRepository _cart;

  Future<SyncReport> run() async {
    final favouritesFailed = !await _uploadFavourites();
    final cart = await _mergeCart();
    return SyncReport(
      favouritesFailed: favouritesFailed,
      cartFailed: cart.failed,
      notMerged: cart.notMerged,
    );
  }

  /// Returns false when the upload failed (local copy kept, Req 10.11).
  Future<bool> _uploadFavourites() async {
    final ids = _favourites.load();
    if (ids.isEmpty) return true;
    try {
      await _client.post('/api/favourites/merge',
          body: {'productIds': ids.toList()});
      await _favourites.clear(); // only after the server confirmed (10.10)
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<({bool failed, List<String> notMerged})> _mergeCart() async {
    final local = _cart.load();
    if (local.isEmpty) return (failed: false, notMerged: const <String>[]);
    try {
      final data = await _client.post('/api/cart/merge', body: {
        'lines': [
          for (final e in local.entries)
            {'productId': e.key, 'quantity': e.value},
        ],
      });
      final rejected = <String, int>{};
      final names = <String>[];
      final raw = data is Map ? data['notMerged'] : null;
      if (raw is List) {
        for (final item in raw) {
          final id = item is Map
              ? (item['productId'] ?? item['id'])?.toString()
              : item?.toString();
          if (id == null) continue;
          final name = item is Map ? item['name']?.toString() : null;
          names.add(name == null || name.isEmpty ? id : name);
          final qty = item is Map && item['quantity'] is num
              ? (item['quantity'] as num).toInt()
              : local[id];
          if (qty != null && qty > 0) {
            rejected[id] = GuestCartRepository.clampQuantity(qty);
          }
        }
      }
      // Keep only what the server did not take (Req 11.12, 11.13).
      await _cart.save(rejected);
      if (rejected.isEmpty) await _cart.clear();
      return (failed: false, notMerged: names);
    } catch (_) {
      return (failed: true, notMerged: const <String>[]);
    }
  }
}

/// Screen-facing session actions.
class AuthActions {
  AuthActions(this._ref);

  final Ref _ref;

  /// Signs in and, for a customer, syncs local favourites and cart. Throws an
  /// [AppFailure] when the sign-in itself fails.
  Future<(AuthUser, SyncReport)> login(String email, String password) async {
    final user = await _ref.read(sessionProvider.notifier).login(email, password);
    if (user.role.isStaff) return (user, const SyncReport());
    final report = await _syncLocalData();
    return (user, report);
  }

  /// Creates the account, then signs in with the same credentials.
  Future<(AuthUser, SyncReport)> register(
      String name, String email, String password) async {
    await _ref.read(apiClientProvider).post('/api/auth/register', body: {
      'name': name.trim(),
      'email': email.trim(),
      'password': password,
    });
    return login(email, password);
  }

  Future<void> logout() => _ref.read(sessionProvider.notifier).logout();

  Future<SyncReport> _syncLocalData() async {
    final LegacyLocalStore store;
    try {
      store = await _ref.read(legacyLocalStoreProvider.future);
    } catch (_) {
      return const SyncReport();
    }
    final report = await PostLoginSync(
      _ref.read(apiClientProvider),
      LocalFavouritesRepository(store),
      GuestCartRepository(store),
    ).run();
    // The in-memory stores were read before the sync; make them re-read.
    _ref.invalidate(cartStoreProvider);
    _ref.invalidate(favoritesStoreProvider);
    return report;
  }
}

final authActionsProvider = Provider<AuthActions>(AuthActions.new);
