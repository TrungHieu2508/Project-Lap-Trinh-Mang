document.addEventListener("DOMContentLoaded", () => {
  // Modal functionality
  const cards = document.querySelectorAll(".card");
  const modal = document.getElementById("modal");
  const modalTitle = document.getElementById("modalTitle");
  const preview = document.getElementById("preview");
  const openMonitorBtn = document.getElementById("openMonitorBtn");
  const closeModal = document.getElementById("closeModal");
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");

  let currentIndex = 0;

  function openModal(index) {
    const card = cards[index];
    if (!card) return;
    currentIndex = index;
    const id = card.dataset.id;
    const link = card.dataset.link;

    modalTitle.textContent = `Phóng to - May ${id}`;
    preview.innerHTML = link && link !== "#" 
      ? `<iframe src="${link}" width="100%" height="100%" frameborder="0"></iframe>`
      : `Preview lớn - Mag ${id}<br><small>Chưa có liên kết</small>`;

    openMonitorBtn.dataset.link = link;
    modal.classList.add("show");
  }

  function closeModalFn() {
    modal.classList.remove("show");
  }

  function openLink() {
    const link = openMonitorBtn.dataset.link;
    if (link && link !== "#") window.open(link, "_blank");
    else alert("Chưa có đường dẫn liên kết!");
  }

  function next() {
    const newIndex = (currentIndex + 1) % cards.length;
    openModal(newIndex);
  }

  function prev() {
    const newIndex = (currentIndex - 1 + cards.length) % cards.length;
    openModal(newIndex);
  }

  cards.forEach((card, i) => card.addEventListener("click", () => openModal(i)));
  closeModal.addEventListener("click", closeModalFn);
  openMonitorBtn.addEventListener("click", openLink);
  nextBtn.addEventListener("click", next);
  prevBtn.addEventListener("click", prev);

  // Keyboard controls
  document.addEventListener("keydown", (e) => {
    if (!modal.classList.contains("show")) return;
    if (e.key === "Escape") closeModalFn();
    if (e.key === "ArrowRight") next();
    if (e.key === "ArrowLeft") prev();
  });

  // Random number generation functionality
  function generateRandomNumber() {
    return Math.floor(Math.random() * 10000).toString().padStart(4, '0');
  }

  const randomNumberElement = document.getElementById('randomNumber');
  randomNumberElement.textContent = generateRandomNumber();

  document.querySelector('.login-btn').addEventListener('click', () => {
    randomNumberElement.textContent = generateRandomNumber();
  });

  // Block/Add machine functionality
  const blockBtn = document.getElementById("blockBtn");
  const addBtn = document.getElementById("addBtn");

  const machines = [
    { id: 1, name: "Máy 1", status: "online" },
    { id: 2, name: "Máy 2", status: "offline" },
    { id: 3, name: "Máy 3", status: "online" },
    { id: 4, name: "Máy 4", status: "offline" }
  ];

  blockBtn.addEventListener("click", () => {
    const selectedMachine = machines.find(machine => machine.status === "online");

    if (selectedMachine) {
      selectedMachine.status = "offline";
      alert(`${selectedMachine.name} đã bị BLOCK!`);
      console.log(`Trạng thái máy ${selectedMachine.name}: ${selectedMachine.status}`);
    } else {
      alert("Không có máy tính online để BLOCK!");
    }
  });

  addBtn.addEventListener("click", () => {
    const newMachine = { id: machines.length + 1, name: `Máy ${machines.length + 1}`, status: "online" };
    machines.push(newMachine);
    alert(`Đã thêm máy: ${newMachine.name}`);
    console.log(`Danh sách máy tính hiện tại:`, machines);
  });
});
