import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/api_client.dart';
import '../../../../core/network/app_failure.dart';
import '../../../orders/data/order_models.dart';
import '../data/staff_orders_repository.dart';

final staffOrdersRepositoryProvider = Provider<StaffOrdersRepository>(
    (ref) => StaffOrdersRepository(ref.watch(apiClientProvider)));

/// Loaded pages of the staff Orders list. A failed refresh or page keeps
/// [orders] and sets [refreshFailed].
class StaffOrdersState {
  const StaffOrdersState({
    this.orders = const [],
    this.hasMore = false,
    this.status,
    this.query = '',
    this.refreshFailed = false,
    this.loadingMore = false,
  });

  final List<StaffOrderSummary> orders;
  final bool hasMore;
  final String? status;
  final String query;
  final bool refreshFailed;
  final bool loadingMore;

  StaffOrdersState copyWith({
    List<StaffOrderSummary>? orders,
    bool? hasMore,
    bool? refreshFailed,
    bool? loadingMore,
  }) =>
      StaffOrdersState(
        orders: orders ?? this.orders,
        hasMore: hasMore ?? this.hasMore,
        status: status,
        query: query,
        refreshFailed: refreshFailed ?? this.refreshFailed,
        loadingMore: loadingMore ?? this.loadingMore,
      );
}

class StaffOrdersNotifier extends AsyncNotifier<StaffOrdersState> {
  String? _status;
  String _query = '';

  @override
  Future<StaffOrdersState> build() => _load();

  Future<StaffOrdersState> _load() async {
    final page = await ref
        .read(staffOrdersRepositoryProvider)
        .list(status: _status, query: _query);
    return StaffOrdersState(
        orders: page.items,
        hasMore: page.hasMore,
        status: _status,
        query: _query);
  }

  /// Applies a status filter and reloads from the first page.
  Future<void> setStatus(String? status) async {
    _status = status;
    await _reloadFresh();
  }

  /// Applies a search text (1 to 100 characters) and reloads.
  Future<void> setQuery(String query) async {
    final q = query.trim();
    _query = q.length > 100 ? q.substring(0, 100) : q;
    await _reloadFresh();
  }

  Future<void> _reloadFresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(_load);
  }

  /// Reloads the first page, keeping the last data when it fails.
  Future<void> refresh() async {
    final previous = state.value;
    try {
      state = AsyncData(await _load());
    } on AppFailure catch (e, st) {
      state = previous == null
          ? AsyncError(e, st)
          : AsyncData(
              previous.copyWith(refreshFailed: true, loadingMore: false));
    }
  }

  Future<void> retry() async {
    if (!state.hasValue) state = const AsyncLoading();
    await refresh();
  }

  Future<void> loadMore() async {
    final current = state.value;
    if (current == null || !current.hasMore || current.loadingMore) return;
    state =
        AsyncData(current.copyWith(loadingMore: true, refreshFailed: false));
    try {
      final page = await ref
          .read(staffOrdersRepositoryProvider)
          .list(status: _status, query: _query, offset: current.orders.length);
      state = AsyncData(StaffOrdersState(
          orders: [...current.orders, ...page.items],
          hasMore: page.hasMore,
          status: _status,
          query: _query));
    } on AppFailure {
      state =
          AsyncData(current.copyWith(refreshFailed: true, loadingMore: false));
    }
  }
}

final staffOrdersProvider =
    AsyncNotifierProvider.autoDispose<StaffOrdersNotifier, StaffOrdersState>(
        StaffOrdersNotifier.new);

class StaffOrderDetailState {
  const StaffOrderDetailState(this.order, {this.refreshFailed = false});
  final OrderDetail order;
  final bool refreshFailed;
}

class StaffOrderDetailNotifier extends AsyncNotifier<StaffOrderDetailState> {
  StaffOrderDetailNotifier(this.orderId);
  final String orderId;

  @override
  Future<StaffOrderDetailState> build() async => StaffOrderDetailState(
      await ref.read(staffOrdersRepositoryProvider).get(orderId));

  Future<void> refresh() async {
    final previous = state.value;
    try {
      final order = await ref.read(staffOrdersRepositoryProvider).get(orderId);
      state = AsyncData(StaffOrderDetailState(order));
    } on AppFailure catch (e, st) {
      state = previous == null
          ? AsyncError(e, st)
          : AsyncData(
              StaffOrderDetailState(previous.order, refreshFailed: true));
    }
  }

  Future<void> retry() async {
    if (!state.hasValue) state = const AsyncLoading();
    await refresh();
  }

  /// Sends the status change. Throws the [AppFailure] on rejection so the
  /// screen can show it; the shown order stays unchanged then.
  Future<void> changeStatus(String status,
      {String? shippingReference, String? reason}) async {
    final order = await ref.read(staffOrdersRepositoryProvider).changeStatus(
        orderId, status,
        shippingReference: shippingReference, reason: reason);
    state = AsyncData(StaffOrderDetailState(order));
  }
}

final staffOrderDetailProvider = AsyncNotifierProvider.autoDispose
    .family<StaffOrderDetailNotifier, StaffOrderDetailState, String>(
        StaffOrderDetailNotifier.new);
