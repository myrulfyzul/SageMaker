import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/api_client.dart';
import '../data/artisan_models.dart';
import '../data/artisans_repository.dart';

final artisansRepositoryProvider = Provider<ArtisansRepository>(
    (ref) => ArtisansRepository(ref.watch(apiClientProvider)));

final artisansProvider = FutureProvider.autoDispose<List<Artisan>>(
    (ref) => ref.watch(artisansRepositoryProvider).list());

final artisanProvider = FutureProvider.autoDispose.family<Artisan, int>(
    (ref, id) => ref.watch(artisansRepositoryProvider).get(id));
