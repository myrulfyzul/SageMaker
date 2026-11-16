import '../../../../core/network/api_client.dart';
import 'artisan_models.dart';

/// `/api/staff/artisans` (Req 23).
class ArtisansRepository {
  ArtisansRepository(this._client);

  final ApiClient _client;

  Future<List<Artisan>> list() async {
    final all = <Artisan>[];
    while (true) {
      final body = await _client.get('/api/staff/artisans',
          query: {'limit': 100, 'offset': all.length});
      final rows =
          body is Map ? (body['items'] as List? ?? const []) : body as List;
      all.addAll(rows
          .map((r) => Artisan.fromJson(Map<String, dynamic>.from(r as Map))));
      final total = body is Map ? (body['total'] as num?)?.toInt() : null;
      if (rows.isEmpty || total == null || all.length >= total) return all;
    }
  }

  Future<Artisan> get(int id) async =>
      Artisan.fromJson(Map<String, dynamic>.from(
          await _client.get('/api/staff/artisans/$id') as Map));

  /// Creates when [id] is null, otherwise edits (Req 23.1).
  Future<ArtisanSaveResult> save({
    int? id,
    required String name,
    required String specialisation,
    required String availability,
    required String story,
    required String phone,
    required String email,
    required String address,
  }) async {
    // Empty contact fields are sent as null: the backend rejects an empty
    // email and `null` clears the stored value.
    String? orNull(String v) => v.trim().isEmpty ? null : v.trim();
    final body = {
      'name': name.trim(),
      'specialisation': specialisation.trim(),
      'availability': availability,
      'story': story,
      'phone': orNull(phone),
      'email': orNull(email),
      'address': orNull(address),
    };
    final res = id == null
        ? await _client.post('/api/staff/artisans', body: body)
        : await _client.put('/api/staff/artisans/$id', body: body);
    final map = Map<String, dynamic>.from(res as Map);
    final ids = <int>[
      for (final w in (map['warnings'] as List? ?? const []))
        if (w is Map)
          for (final j in (w['jobIds'] as List? ?? const []))
            if (j is num) j.toInt(),
    ];
    return ArtisanSaveResult(Artisan.fromJson(map), ids);
  }
}
