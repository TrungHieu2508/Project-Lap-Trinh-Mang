// Simulating the data for machines and images.
const machines = [
  { id: 1, name: "Máy 1", images: [
    { url: "image1.jpg", time: "10:00 AM" },
    { url: "image2.jpg", time: "10:05 AM" },
  ] },
  { id: 2, name: "Máy 2", images: [
    { url: "image3.jpg", time: "11:00 AM" },
    { url: "image4.jpg", time: "11:10 AM" },
  ] },
  { id: 3, name: "Máy 3", images: [
    { url: "image5.jpg", time: "12:00 PM" },
    { url: "image6.jpg", time: "12:15 PM" },
  ] },
];

function loadMachineOptions() {
  const machineSelect = document.getElementById("machineSelect");
  machines.forEach(machine => {
    const option = document.createElement("option");
    option.value = machine.id;
    option.textContent = machine.name;
    machineSelect.appendChild(option);
  });
}

function loadImages() {
  const machineId = document.getElementById("machineSelect").value;
  const imageGallery = document.getElementById("imageGallery");
  imageGallery.innerHTML = "";  // Clear the gallery before adding new images

  if (!machineId) {
    return;
  }

  const selectedMachine = machines.find(machine => machine.id == machineId);
  if (selectedMachine && selectedMachine.images.length) {
    selectedMachine.images.forEach(image => {
      const row = document.createElement("tr");

      const imgCell = document.createElement("td");
      const imgElement = document.createElement("img");
      imgElement.src = image.url;
      imgElement.alt = "Hình ảnh giám sát";
      imgCell.appendChild(imgElement);

      const nameCell = document.createElement("td");
      nameCell.textContent = selectedMachine.name;

      const timeCell = document.createElement("td");
      timeCell.textContent = image.time;

      row.appendChild(imgCell);
      row.appendChild(nameCell);
      row.appendChild(timeCell);

      imageGallery.appendChild(row);
    });
  }
}

function searchMachine() {
  const searchValue = document.getElementById("searchBox").value.toLowerCase();
  const machineSelect = document.getElementById("machineSelect");
  const options = machineSelect.options;

  for (let i = 0; i < options.length; i++) {
    const option = options[i];
    if (option.textContent.toLowerCase().includes(searchValue)) {
      option.style.display = "block"; // Show matching options
    } else {
      option.style.display = "none"; // Hide non-matching options
    }
  }
}

// Initialize page
document.addEventListener("DOMContentLoaded", function() {
  loadMachineOptions(); // Load machine options into the select menu
});
