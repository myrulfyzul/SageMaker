import 'package:flutter/material.dart';

import 'vimeo_player_io.dart'
    if (dart.library.js_interop) 'vimeo_player_web.dart' as impl;

/// Embedded Vimeo player: an iframe on web, a WebView on Android and iOS.
/// Build it only after the user taps play, so nothing loads up front.
class VimeoPlayer extends StatelessWidget {
  const VimeoPlayer({super.key, required this.videoId});
  final String videoId;

  /// Player URL with autoplay, since it opens after a tap.
  static String embedUrl(String id) =>
      'https://player.vimeo.com/video/$id?autoplay=1&title=0&byline=0&portrait=0&dnt=1';

  @override
  Widget build(BuildContext context) =>
      impl.buildVimeoPlayer(embedUrl(videoId));
}
