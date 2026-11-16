import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/api_client.dart';
import '../../../../core/network/app_failure.dart';
import '../data/analytics_models.dart';

final analyticsRepositoryProvider = Provider<AnalyticsRepository>(
    (ref) => AnalyticsRepository(ref.watch(apiClientProvider)));

/// Loaded value plus whether the latest refresh failed; the previous values
/// stay on screen after a failure (Req 19.8).
class Loaded<T> {
  const Loaded(this.data, {this.refreshFailed = false});
  final T data;
  final bool refreshFailed;
}

class DashboardNotifier extends AsyncNotifier<Loaded<DashboardData>> {
  @override
  Future<Loaded<DashboardData>> build() async =>
      Loaded(await ref.read(analyticsRepositoryProvider).dashboard());

  Future<void> refresh() async {
    final previous = state.value;
    try {
      final data = await ref.read(analyticsRepositoryProvider).dashboard();
      state = AsyncData(Loaded(data));
    } on AppFailure catch (e, st) {
      state = previous == null
          ? AsyncError(e, st)
          : AsyncData(Loaded(previous.data, refreshFailed: true));
    }
  }

  Future<void> retry() async {
    if (!state.hasValue) state = const AsyncLoading();
    await refresh();
  }
}

final dashboardProvider = AsyncNotifierProvider.autoDispose<DashboardNotifier,
    Loaded<DashboardData>>(DashboardNotifier.new);

/// Analytics screen state: chosen range, local or server range error, and the
/// last good report.
class AnalyticsState {
  const AnalyticsState({
    required this.start,
    required this.end,
    this.report,
    this.rangeError,
    this.loading = false,
    this.loadFailed = false,
  });

  final DateTime start;
  final DateTime end;
  final SalesReport? report;
  final String? rangeError;
  final bool loading;
  final bool loadFailed;

  AnalyticsState copyWith({
    DateTime? start,
    DateTime? end,
    SalesReport? report,
    String? rangeError,
    bool clearRangeError = false,
    bool? loading,
    bool? loadFailed,
  }) =>
      AnalyticsState(
        start: start ?? this.start,
        end: end ?? this.end,
        report: report ?? this.report,
        rangeError: clearRangeError ? null : (rangeError ?? this.rangeError),
        loading: loading ?? this.loading,
        loadFailed: loadFailed ?? this.loadFailed,
      );
}

/// Default range: the current month and the five before it.
DateTime defaultRangeStart(DateTime now) =>
    DateTime(now.year, now.month - 5, 1);

class AnalyticsNotifier extends Notifier<AnalyticsState> {
  @override
  AnalyticsState build() {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    Future.microtask(load);
    return AnalyticsState(
        start: defaultRangeStart(today), end: today, loading: true);
  }

  Future<void> setRange({DateTime? start, DateTime? end}) async {
    state = state.copyWith(start: start, end: end);
    await load();
  }

  Future<void> load() async {
    final s = state.start;
    final e = state.end;
    final err = validateRange(s, e);
    if (err != null) {
      // Invalid range: no request, keep the previous report (Req 26.4, 26.6).
      state = state.copyWith(rangeError: err, loading: false);
      return;
    }
    state = state.copyWith(
        clearRangeError: true, loading: true, loadFailed: false);
    try {
      final report = await ref.read(analyticsRepositoryProvider).sales(s, e);
      if (state.start != s || state.end != e) return;
      state = state.copyWith(report: report, loading: false);
    } on ValidationFailure catch (v) {
      state = state.copyWith(rangeError: v.message, loading: false);
    } on AppFailure {
      state = state.copyWith(loading: false, loadFailed: true);
    }
  }
}

final analyticsProvider =
    NotifierProvider.autoDispose<AnalyticsNotifier, AnalyticsState>(
        AnalyticsNotifier.new);
