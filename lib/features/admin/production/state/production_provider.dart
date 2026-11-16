import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/api_client.dart';
import '../../../auth/data/auth_user.dart';
import '../../../auth/state/session_provider.dart';
import '../data/production_models.dart';
import '../data/production_repository.dart';

final productionRepositoryProvider = Provider<ProductionRepository>(
    (ref) => ProductionRepository(ref.watch(apiClientProvider)));

/// Role of the signed-in user; an Artisan_User gets the restricted view
/// (Req 6.7, 6.8). Overridable in tests.
final productionRoleProvider = Provider<AppRole>((ref) {
  final s = ref.watch(sessionProvider);
  return s is SessionSignedIn ? s.role : AppRole.customer;
});

class ProductionFiltersNotifier extends Notifier<ProductionFilters> {
  @override
  ProductionFilters build() => const ProductionFilters();

  void set(ProductionFilters f) => state = f;
}

final productionFiltersProvider =
    NotifierProvider.autoDispose<ProductionFiltersNotifier, ProductionFilters>(
        ProductionFiltersNotifier.new);

final productionJobsProvider = FutureProvider.autoDispose<List<ProductionJob>>(
    (ref) => ref
        .watch(productionRepositoryProvider)
        .list(ref.watch(productionFiltersProvider)));

final productionJobProvider = FutureProvider.autoDispose
    .family<ProductionJob, int>(
        (ref, id) => ref.watch(productionRepositoryProvider).get(id));
