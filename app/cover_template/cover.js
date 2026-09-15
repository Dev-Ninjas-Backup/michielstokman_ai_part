/**
 * Cover dynamic API
 *
 * Cover.set({ gender: 'male', orientation: 'homosexual', age: 31, author: 'Alex' })
 * Cover.get()
 */
(function (global) {
  var ASSETS = {
    genderIcon: {
      female: "./assets/icon-female.svg",
      male: "./assets/icon-male.svg",
    },
    genderBg: {
      female: "./assets/badge-female-shape.png",
      male: "./assets/badge-male-shape.png",
    },
    orientationBg: "./assets/badge-bisexual.png",
  };

  var LONG_ORIENTATION = 10; /* chars — homosexual etc. */

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function coverEl() {
    return document.getElementById("cover");
  }

  function bindText(cover, key, value) {
    cover.querySelectorAll('[data-bind="' + key + '"]').forEach(function (el) {
      if (key === "confession") {
        /* keep line breaks sensible for long copy */
        el.textContent = value;
        return;
      }
      if (key === "city" && value && value.slice(-1) !== "," && value.slice(-2) !== ", ") {
        el.textContent = value.replace(/,\s*$/, "") + ", ";
        return;
      }
      el.textContent = value == null ? "" : String(value);
    });
  }

  function setGender(cover, gender) {
    // Only male/female assets exist in Figma exports (icon + badge shape).
    // Unknown/empty values deliberately fall back to "female" — asset limitation,
    // not a data-modeling choice. A neutral/unspecified state needs a third
    // icon+badge from Figma before it can be supported without faking female.
    var g = String(gender || "female").toLowerCase();
    if (g !== "male" && g !== "female") g = "female";

    cover.setAttribute("data-gender", g);
    bindText(cover, "gender", g);

    var chip = $('[data-chip="gender"]', cover);
    if (chip) {
      chip.setAttribute("data-gender", g);
      chip.classList.toggle("is-long", g.length >= 8);
      var bg = $(".chip__bg", chip);
      var icon = $("[data-gender-icon]", chip);
      if (bg) bg.src = ASSETS.genderBg[g] || ASSETS.genderBg.female;
      if (icon) {
        icon.src = ASSETS.genderIcon[g] || ASSETS.genderIcon.female;
        if (g === "male") {
          icon.setAttribute("width", "97");
          icon.setAttribute("height", "97");
        } else {
          icon.setAttribute("width", "76");
          icon.setAttribute("height", "110");
        }
      }
    }
  }

  function setOrientation(cover, orientation) {
    var o = String(orientation || "bisexual").toLowerCase();
    cover.setAttribute("data-orientation", o);
    bindText(cover, "orientation", o);

    var chip = $('[data-chip="orientation"]', cover);
    if (!chip) return;

    chip.setAttribute("data-orientation", o);
    chip.classList.toggle("is-long", o.length >= LONG_ORIENTATION);
    chip.classList.toggle("is-xlong", o.length >= 12);

    var bg = $(".chip__bg", chip);
    if (bg) bg.src = ASSETS.orientationBg;
  }

  function setAge(cover, age) {
    var a = String(age);
    cover.setAttribute("data-age", a);
    bindText(cover, "age", a);
  }

  function setAuthor(cover, author, role) {
    var chip = $('[data-chip="author"]', cover);
    if (author != null) {
      cover.setAttribute("data-author", author);
      bindText(cover, "author", author);
      if (chip) {
        var n = String(author).trim().length;
        chip.classList.toggle("is-long", n >= 8);
        chip.classList.toggle("is-xlong", n >= 11);
      }
    }
    if (role != null) {
      cover.setAttribute("data-role", role);
      bindText(cover, "role", role);
    }
  }

  function setConfession(cover, text) {
    if (text == null) return;
    cover.setAttribute("data-confession", text);
    bindText(cover, "confession", text.replace(/\n/g, " ").trim());
  }

  function setTitles(cover, data) {
    ["title-line1", "title-line2", "subtitle-line1", "subtitle-line2"].forEach(
      function (key) {
        if (data[key] != null) {
          cover.setAttribute("data-" + key, data[key]);
          bindText(cover, key, data[key]);
        }
      }
    );
  }

  function setLocation(cover, city, country) {
    if (city != null) {
      cover.setAttribute("data-city", city);
      bindText(cover, "city", city);
    }
    if (country != null) {
      cover.setAttribute("data-country", country);
      bindText(cover, "country", country);
    }
  }

  // Photo is a static <img> in markup; Cover.set originally had no photo key.
  // photoUrl / photo swaps .photo-image img src (data URI or http(s) / relative path).
  function setPhoto(cover, url) {
    if (url == null || url === "") return;
    var img = $(".photo-image img", cover);
    if (img) img.src = url;
  }

  function setExplicit(cover, value) {
    // Visibility: null | false | "" hide the chip; true | string show it.
    // true → default label "explicit"; string → custom label (within hard limit).
    var hide =
      value === null ||
      value === false ||
      value === "" ||
      value === undefined;

    if (hide) {
      cover.classList.add("is-explicit-hidden");
      cover.removeAttribute("data-explicit");
      return;
    }

    cover.classList.remove("is-explicit-hidden");
    var label = value === true ? "explicit" : String(value);
    cover.setAttribute("data-explicit", label);
    bindText(cover, "explicit", label);
  }

  /**
   * Largest font-size that keeps copy within ``maxLines`` inside the beige
   * column (max-width). Shrinks long titles like "The Iron and the Grain" so
   * they fill horizontal space without clipping or crossing the torn edge.
   * If even ``minPx`` overflows, keeps shrinking down to ``floorPx``.
   */
  function fitBlockFont(el, minPx, maxPx, maxLines, floorPx) {
    if (!el) return;
    var text = (el.textContent || "").replace(/\s+/g, " ").trim();
    if (!text) {
      el.style.fontSize = "";
      return;
    }
    var lineRatio = 1.2;
    var floor = floorPx != null ? floorPx : Math.max(24, Math.floor(minPx * 0.5));
    var lo = minPx;
    var hi = maxPx;
    var best = minPx;
    function maxH(px) {
      return px * lineRatio * maxLines + 2;
    }
    function fits(px) {
      el.style.fontSize = px + "px";
      return el.scrollHeight <= maxH(px);
    }
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      if (fits(mid)) {
        best = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    while (best > floor && !fits(best)) {
      best -= 1;
    }
    el.style.fontSize = best + "px";
  }

  function fitCopyFonts(cover) {
    cover = cover || coverEl();
    if (!cover) return;
    fitBlockFont($(".title-main", cover), 88, 164, 2, 72);
    fitBlockFont($(".subtitle", cover), 48, 80, 2, 30);
  }

  function afterFonts(fn) {
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(fn).catch(fn);
    } else {
      fn();
    }
  }

  function applyFromDataset(cover) {
    var d = cover.dataset;
    setTitles(cover, {
      "title-line1": d.titleLine1,
      "title-line2": d.titleLine2,
      "subtitle-line1": d.subtitleLine1,
      "subtitle-line2": d.subtitleLine2,
    });
    if (d.confession) setConfession(cover, d.confession);
    setLocation(cover, d.city, d.country);
    setAuthor(cover, d.author, d.role);
    if (d.age) setAge(cover, d.age);
    if (d.gender) setGender(cover, d.gender);
    if (d.orientation) setOrientation(cover, d.orientation);
    // Absent / empty data-explicit → hide; present string → show
    if (cover.hasAttribute("data-explicit") && d.explicit) {
      setExplicit(cover, d.explicit);
    } else {
      setExplicit(cover, null);
    }
  }

  function set( partial ) {
    var cover = coverEl();
    if (!cover || !partial) return get();

    if (partial.gender != null) setGender(cover, partial.gender);
    if (partial.orientation != null) setOrientation(cover, partial.orientation);
    if (partial.age != null) setAge(cover, partial.age);
    if (partial.author != null || partial.role != null) {
      setAuthor(cover, partial.author, partial.role);
    }
    if (partial.confession != null) setConfession(cover, partial.confession);
    if (partial.city != null || partial.country != null) {
      setLocation(cover, partial.city, partial.country);
    }
    // Use `in` so explicit: null | false is applied (hides chip)
    if ("explicit" in partial) setExplicit(cover, partial.explicit);
    if (partial.photoUrl != null || partial.photo != null) {
      setPhoto(cover, partial.photoUrl != null ? partial.photoUrl : partial.photo);
    }
    if (
      partial["title-line1"] != null ||
      partial.titleLine1 != null ||
      partial["title-line2"] != null ||
      partial.titleLine2 != null ||
      partial["subtitle-line1"] != null ||
      partial.subtitleLine1 != null ||
      partial["subtitle-line2"] != null ||
      partial.subtitleLine2 != null
    ) {
      setTitles(cover, {
        "title-line1": partial["title-line1"] ?? partial.titleLine1,
        "title-line2": partial["title-line2"] ?? partial.titleLine2,
        "subtitle-line1": partial["subtitle-line1"] ?? partial.subtitleLine1,
        "subtitle-line2": partial["subtitle-line2"] ?? partial.subtitleLine2,
      });
    }

    fitCopyFonts(cover);
    return get();
  }

  function get() {
    var cover = coverEl();
    if (!cover) return null;
    var d = cover.dataset;
    return {
      titleLine1: d.titleLine1,
      titleLine2: d.titleLine2,
      subtitleLine1: d.subtitleLine1,
      subtitleLine2: d.subtitleLine2,
      confession: d.confession,
      city: d.city,
      country: d.country,
      author: d.author,
      role: d.role,
      age: d.age,
      gender: d.gender,
      orientation: d.orientation,
      explicit: cover.classList.contains("is-explicit-hidden")
        ? false
        : d.explicit || false,
    };
  }

  function fit() {
    var cover = coverEl();
    if (!cover) return;
    var size = Math.min(window.innerWidth, window.innerHeight);
    cover.style.transform = "scale(" + size / 2160 + ")";
  }

  function init() {
    var cover = coverEl();
    if (!cover) return;
    applyFromDataset(cover);
    afterFonts(function () {
      fitCopyFonts(cover);
      fit();
    });
    window.addEventListener("resize", fit);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  global.Cover = {
    set: set,
    get: get,
    fit: fit,
    fitCopyFonts: fitCopyFonts,
    assets: ASSETS,
  };
})(typeof window !== "undefined" ? window : this);
