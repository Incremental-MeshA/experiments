CXX ?= c++
CXXFLAGS ?= -O3 -DNDEBUG -std=c++17 -Wall -Wextra -Wpedantic
CPPFLAGS += -Iinclude
BUILD ?= build
HEADERS := $(wildcard include/ima/*.hpp)

.PHONY: all clean test sanitize
all: $(BUILD)/mesh_bench $(BUILD)/mesh_tests

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/mesh_bench: src/benchmark.cpp $(HEADERS) Makefile | $(BUILD)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) '-DIMA_BUILD_FLAGS="$(CXXFLAGS)"' $< -o $@

$(BUILD)/mesh_tests: tests/selfcheck.cpp $(HEADERS) Makefile | $(BUILD)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) '-DIMA_BUILD_FLAGS="$(CXXFLAGS)"' $< -o $@

test: all
	$(BUILD)/mesh_tests data/car16_md.txt data/legacy8.txt

sanitize:
	$(MAKE) BUILD=build-sanitize CXXFLAGS='-O1 -g -std=c++17 -Wall -Wextra -Wpedantic -fsanitize=address,undefined -fno-omit-frame-pointer' all

clean:
	rm -rf $(BUILD)
