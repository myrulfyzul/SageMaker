import 'dart:ui_web' as ui_web;

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

final _registered = <String>{};

/// Web: the Vimeo player page in an iframe.
Widget buildVimeoPlayer(String url) {
  final viewType = 'vimeo-${url.hashCode}';
  if (_registered.add(viewType)) {
    ui_web.platformViewRegistry.registerViewFactory(viewType, (int _) {
      final frame = web.HTMLIFrameElement()
        ..src = url
        ..allow = 'autoplay; fullscreen; picture-in-picture'
        ..allowFullscreen = true;
      frame.style
        ..border = '0'
        ..width = '100%'
        ..height = '100%';
      return frame;
    });
  }
  return HtmlElementView(viewType: viewType);
}
