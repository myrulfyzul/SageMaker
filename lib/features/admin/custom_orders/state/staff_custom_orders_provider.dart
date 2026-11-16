import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/api_client.dart';
import '../data/staff_custom_orders.dart';

final staffCustomOrdersRepositoryProvider =
    Provider<StaffCustomOrdersRepository>(
        (ref) => StaffCustomOrdersRepository(ref.watch(apiClientProvider)));

/// Selected status filter; null shows all (Req 25.2).
class CustomOrderFilter extends Notifier<String?> {
  @override
  String? build() => null;
  void set(String? v) => state = v;
}

final customOrderFilterProvider =
    NotifierProvider.autoDispose<CustomOrderFilter, String?>(
        CustomOrderFilter.new);

/// First page of custom orders, newest first (Req 25.1). Pages append via
/// [StaffCustomOrdersNotifier.loadMore].
class StaffCustomOrdersNotifier
    extends AsyncNotifier<StaffCustomOrderPage> {
  @override
  Future<StaffCustomOrderPage> build() => ref
      .watch(staffCustomOrdersRepositoryProvider)
      .list(status: ref.watch(customOrderFilterProvider));

  Future<void> loadMore() async {
    final c = state.value;
    if (c == null || !c.hasMore) return;
    final next = await ref
        .read(staffCustomOrdersRepositoryProvider)
        .list(status: ref.read(customOrderFilterProvider), offset: c.items.length);
    state = AsyncData(
        StaffCustomOrderPage([...c.items, ...next.items], next.total));
  }
}

final staffCustomOrdersProvider = AsyncNotifierProvider.autoDispose<
    StaffCustomOrdersNotifier,
    StaffCustomOrderPage>(StaffCustomOrdersNotifier.new);

final assignableArtisansProvider =
    FutureProvider.autoDispose<List<AssignableArtisan>>(
        (ref) => ref.watch(staffCustomOrdersRepositoryProvider).activeArtisans());

