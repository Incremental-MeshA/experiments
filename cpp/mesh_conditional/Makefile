CXX ?= g++
CXXFLAGS ?= -O3 -DNDEBUG -std=c++17 -Wall -Wextra -Wpedantic
INCLUDES := -I../include -I../experiments -I../mesh_variants -I../navigation_sweeps
HEADERS := $(wildcard *.hpp ../include/ima/*.hpp ../navigation_sweeps/*.hpp ../navigation_controls/*.hpp ../mpgaa_mesh/*.hpp ../mpgaa_lazy/*.hpp ../mesh_envelope/*.hpp) ../experiments/memory.hpp ../experiments/dstar_boundary.hpp ../mesh_variants/variants.hpp
.PHONY: all test sanitize
all: build/replay build/replay_memory build/navigation build/navigation_memory build/test
build:
	mkdir -p $@
build/replay: replay.cpp $(HEADERS) Makefile | build
	$(CXX) $(INCLUDES) $(CXXFLAGS) '-DIMA_EXPERIMENT_FLAGS="$(CXXFLAGS)"' $< -o $@
build/replay_memory: replay.cpp $(HEADERS) Makefile | build
	$(CXX) $(INCLUDES) $(CXXFLAGS) -DIMA_TRACK_ALLOC '-DIMA_EXPERIMENT_FLAGS="$(CXXFLAGS) -DIMA_TRACK_ALLOC"' $< -o $@
build/navigation: navigation.cpp $(HEADERS) Makefile | build
	$(CXX) $(INCLUDES) $(CXXFLAGS) '-DNAV_FLAGS="$(CXXFLAGS)"' $< -o $@
build/navigation_memory: navigation.cpp $(HEADERS) Makefile | build
	$(CXX) $(INCLUDES) $(CXXFLAGS) -DIMA_TRACK_ALLOC '-DNAV_FLAGS="$(CXXFLAGS) -DIMA_TRACK_ALLOC"' $< -o $@
build/test: test.cpp $(HEADERS) Makefile | build
	$(CXX) $(INCLUDES) $(CXXFLAGS) $< -o $@
test: build/test
	build/test ../experiments/frozen/grid8_model.txt
	build/test ../experiments/frozen/car16_model.txt
sanitize: | build
	$(CXX) $(INCLUDES) -O1 -g -std=c++17 -fsanitize=address,undefined -fno-omit-frame-pointer test.cpp -o build/test_sanitize
