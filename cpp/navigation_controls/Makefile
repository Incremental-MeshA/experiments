CXX ?= g++
CXXFLAGS ?= -O3 -DNDEBUG -std=c++17 -Wall -Wextra -Wpedantic
INCLUDES := -I../include -I../experiments -I../mesh_variants -I../navigation_sweeps
HEADERS := $(wildcard *.hpp ../include/ima/*.hpp ../navigation_sweeps/*.hpp) ../experiments/memory.hpp ../experiments/dstar_boundary.hpp ../mesh_variants/variants.hpp
.PHONY: all test sanitize
all: build/experiment build/experiment_memory build/test
build:
	mkdir -p $@
build/experiment: bench.cpp $(HEADERS) Makefile | build
	$(CXX) $(INCLUDES) $(CXXFLAGS) '-DNAV_FLAGS="$(CXXFLAGS)"' $< -o $@
build/experiment_memory: bench.cpp $(HEADERS) Makefile | build
	$(CXX) $(INCLUDES) $(CXXFLAGS) -DIMA_TRACK_ALLOC '-DNAV_FLAGS="$(CXXFLAGS) -DIMA_TRACK_ALLOC"' $< -o $@
build/test: test.cpp strong_grid.hpp ../experiments/memory.hpp $(wildcard ../include/ima/*.hpp) | build
	$(CXX) $(INCLUDES) $(CXXFLAGS) $< -o $@
test: build/test
	build/test ../navigation_sweeps/frozen/grid8_model.txt
sanitize: | build
	$(CXX) $(INCLUDES) -O1 -g -std=c++17 -fsanitize=address,undefined -fno-omit-frame-pointer -DIMA_TRACK_ALLOC test.cpp -o build/test_sanitize
	build/test_sanitize ../navigation_sweeps/frozen/grid8_model.txt
