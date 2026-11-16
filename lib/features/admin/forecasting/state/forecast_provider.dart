import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/api_client.dart';
import '../data/forecast_models.dart';

final forecastRepositoryProvider = Provider<ForecastRepository>(
    (ref) => ForecastRepository(ref.watch(apiClientProvider)));

final forecastProvider = FutureProvider.autoDispose.family<Forecast, String>(
    (ref, productId) => ref.watch(forecastRepositoryProvider).get(productId));
