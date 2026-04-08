(function () {
  function updateUploadLabel(fileInput, textElement) {
    if (!fileInput || !textElement) {
      return;
    }

    if (fileInput.files && fileInput.files.length > 1) {
      textElement.textContent = `${fileInput.files.length} photos selected`;
      textElement.classList.add('has-files');
      return;
    }

    if (fileInput.files && fileInput.files.length === 1) {
      textElement.textContent = fileInput.files[0].name;
      textElement.classList.add('has-files');
      return;
    }

    textElement.textContent = 'Click or drag photos here';
    textElement.classList.remove('has-files');
  }

  document.addEventListener('DOMContentLoaded', function () {
    const inputs = document.querySelectorAll(
      '.post-form-card input[type="text"], .post-form-card input[type="number"], .post-form-card textarea'
    );

    inputs.forEach(input => {
      input.classList.add('form-control');
    });

    const fileInput = document.getElementById('id_images');
    const textElement = document.getElementById('file-upload-text');
    if (fileInput && textElement) {
      fileInput.addEventListener('change', function () {
        updateUploadLabel(fileInput, textElement);
      });
      updateUploadLabel(fileInput, textElement);
    }

    if (typeof L === 'undefined') {
      return;
    }

    const mapElement = document.getElementById('map');
    if (!mapElement) {
      return;
    }

    const map = L.map('map').setView([47.1585, 27.6014], 13);

    // Ensure correct sizing inside the fixed-height flex card
    setTimeout(() => map.invalidateSize(), 60);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap',
    }).addTo(map);

    let marker;
    const latInput = document.getElementById('id_lat');
    const lngInput = document.getElementById('id_lng');

    function updateMapFromInputs() {
      if (!latInput || !lngInput) {
        return;
      }

      const lat = parseFloat(latInput.value);
      const lng = parseFloat(lngInput.value);

      if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
        return;
      }

      if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
        return;
      }

      const newLatLng = [lat, lng];
      if (marker) {
        marker.setLatLng(newLatLng);
      } else {
        marker = L.marker(newLatLng).addTo(map);
      }

      map.setView(newLatLng, map.getZoom());
    }

    if (latInput && latInput.value && lngInput && lngInput.value) {
      updateMapFromInputs();
      map.setView([parseFloat(latInput.value), parseFloat(lngInput.value)], 15);
    }

    if (latInput && lngInput) {
      latInput.addEventListener('input', updateMapFromInputs);
      lngInput.addEventListener('input', updateMapFromInputs);
    }

    map.on('click', function (event) {
      const clickedLat = event.latlng.lat;
      const clickedLng = event.latlng.lng;

      if (marker) {
        marker.setLatLng(event.latlng);
      } else {
        marker = L.marker(event.latlng).addTo(map);
      }

      if (latInput && lngInput) {
        latInput.value = clickedLat.toFixed(6);
        lngInput.value = clickedLng.toFixed(6);
      }
    });
  });
})();
